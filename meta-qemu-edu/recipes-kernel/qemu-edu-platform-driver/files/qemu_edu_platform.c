// SPDX-License-Identifier: GPL-2.0-only
#include <linux/atomic.h>
#include <linux/device.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/slab.h>

#define QEMU_EDU_PLATFORM_ID 0x0100a64e
#define QEMU_EDU_PLATFORM_ID_REG 0x00
#define QEMU_EDU_PLATFORM_SCRATCH_REG 0x04
#define QEMU_EDU_PLATFORM_IRQ_STATUS_REG 0x20
#define QEMU_EDU_PLATFORM_IRQ_RAISE_REG 0x60
#define QEMU_EDU_PLATFORM_IRQ_ACK_REG 0x64
#define QEMU_EDU_PLATFORM_REQUIRED_SIZE 0x68

struct qemu_edu_platform {
	void __iomem *base;
	int irq;
	atomic_t irq_count;
	u32 last_irq_status;
};

static irqreturn_t qemu_edu_platform_irq(int irq, void *opaque)
{
	struct qemu_edu_platform *edu = opaque;
	u32 status = readl(edu->base + QEMU_EDU_PLATFORM_IRQ_STATUS_REG);

	if (!status)
		return IRQ_NONE;

	writel(status, edu->base + QEMU_EDU_PLATFORM_IRQ_ACK_REG);
	WRITE_ONCE(edu->last_irq_status, status);
	atomic_inc(&edu->irq_count);
	return IRQ_HANDLED;
}

static ssize_t identification_show(struct device *dev,
				   struct device_attribute *attr, char *buf)
{
	struct qemu_edu_platform *edu = dev_get_drvdata(dev);

	return sysfs_emit(buf, "0x%08x\n",
			  readl(edu->base + QEMU_EDU_PLATFORM_ID_REG));
}
static DEVICE_ATTR_RO(identification);

static ssize_t scratch_show(struct device *dev, struct device_attribute *attr,
			    char *buf)
{
	struct qemu_edu_platform *edu = dev_get_drvdata(dev);

	return sysfs_emit(buf, "0x%08x\n",
			  readl(edu->base + QEMU_EDU_PLATFORM_SCRATCH_REG));
}

static ssize_t scratch_store(struct device *dev, struct device_attribute *attr,
			     const char *buf, size_t count)
{
	struct qemu_edu_platform *edu = dev_get_drvdata(dev);
	u32 value;
	int ret;

	ret = kstrtou32(buf, 0, &value);
	if (ret)
		return ret;
	writel(value, edu->base + QEMU_EDU_PLATFORM_SCRATCH_REG);
	return count;
}
static DEVICE_ATTR_RW(scratch);

static ssize_t interrupt_count_show(struct device *dev,
				    struct device_attribute *attr, char *buf)
{
	struct qemu_edu_platform *edu = dev_get_drvdata(dev);

	return sysfs_emit(buf, "%d\n", atomic_read(&edu->irq_count));
}
static DEVICE_ATTR_RO(interrupt_count);

static ssize_t last_irq_status_show(struct device *dev,
				    struct device_attribute *attr, char *buf)
{
	struct qemu_edu_platform *edu = dev_get_drvdata(dev);

	return sysfs_emit(buf, "0x%08x\n", READ_ONCE(edu->last_irq_status));
}
static DEVICE_ATTR_RO(last_irq_status);

static ssize_t raise_irq_store(struct device *dev,
			       struct device_attribute *attr,
			       const char *buf, size_t count)
{
	struct qemu_edu_platform *edu = dev_get_drvdata(dev);
	u32 value;
	int ret;

	ret = kstrtou32(buf, 0, &value);
	if (ret)
		return ret;
	if (!value)
		return -EINVAL;
	writel(value, edu->base + QEMU_EDU_PLATFORM_IRQ_RAISE_REG);
	return count;
}
static DEVICE_ATTR_WO(raise_irq);

static struct attribute *qemu_edu_platform_attrs[] = {
	&dev_attr_identification.attr,
	&dev_attr_scratch.attr,
	&dev_attr_interrupt_count.attr,
	&dev_attr_last_irq_status.attr,
	&dev_attr_raise_irq.attr,
	NULL,
};
ATTRIBUTE_GROUPS(qemu_edu_platform);

static int qemu_edu_platform_probe(struct platform_device *pdev)
{
	struct qemu_edu_platform *edu;
	struct resource *resource;
	u32 identification;
	int ret;

	edu = devm_kzalloc(&pdev->dev, sizeof(*edu), GFP_KERNEL);
	if (!edu)
		return -ENOMEM;

	resource = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	if (!resource || resource_size(resource) < QEMU_EDU_PLATFORM_REQUIRED_SIZE)
		return dev_err_probe(&pdev->dev, -EINVAL,
				     "MMIO resource is absent or too small\n");
	edu->base = devm_ioremap_resource(&pdev->dev, resource);
	if (IS_ERR(edu->base))
		return PTR_ERR(edu->base);

	edu->irq = platform_get_irq(pdev, 0);
	if (edu->irq < 0)
		return edu->irq;

	identification = readl(edu->base + QEMU_EDU_PLATFORM_ID_REG);
	if (identification != QEMU_EDU_PLATFORM_ID)
		return dev_err_probe(&pdev->dev, -ENODEV,
				     "unexpected identification 0x%08x\n",
				     identification);

	atomic_set(&edu->irq_count, 0);
	WRITE_ONCE(edu->last_irq_status, 0);
	writel(~0U, edu->base + QEMU_EDU_PLATFORM_IRQ_ACK_REG);
	ret = devm_request_irq(&pdev->dev, edu->irq, qemu_edu_platform_irq, 0,
			       dev_name(&pdev->dev), edu);
	if (ret)
		return dev_err_probe(&pdev->dev, ret, "cannot request interrupt\n");

	platform_set_drvdata(pdev, edu);
	ret = device_add_group(&pdev->dev, &qemu_edu_platform_group);
	if (ret)
		return dev_err_probe(&pdev->dev, ret, "cannot add sysfs group\n");

	dev_info(&pdev->dev, "educational platform device ready\n");
	return 0;
}

static void qemu_edu_platform_remove(struct platform_device *pdev)
{
	struct qemu_edu_platform *edu = platform_get_drvdata(pdev);

	device_remove_group(&pdev->dev, &qemu_edu_platform_group);
	writel(~0U, edu->base + QEMU_EDU_PLATFORM_IRQ_ACK_REG);
	synchronize_irq(edu->irq);
}

static const struct of_device_id qemu_edu_platform_of_match[] = {
	{ .compatible = "qemu,edu-platform" },
	{ }
};
MODULE_DEVICE_TABLE(of, qemu_edu_platform_of_match);

static struct platform_driver qemu_edu_platform_driver = {
	.probe = qemu_edu_platform_probe,
	.remove = qemu_edu_platform_remove,
	.driver = {
		.name = "qemu_edu_platform",
		.of_match_table = qemu_edu_platform_of_match,
	},
};
module_platform_driver(qemu_edu_platform_driver);

MODULE_AUTHOR("Yocto QEMU EDU learning project contributors");
MODULE_DESCRIPTION("Driver for the QEMU EDU platform teaching device");
MODULE_LICENSE("GPL");
