// SPDX-License-Identifier: GPL-2.0-only
/*
 * qemu_edu.c - small learning driver for QEMU's EDU PCI device
 *
 * The device specification is documented by QEMU under
 * docs/specs/edu.rst.  This driver intentionally uses legacy INTx first;
 * converting it to MSI is a useful follow-up exercise.
 */

#include <linux/atomic.h>
#include <linux/completion.h>
#include <linux/dma-mapping.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/jiffies.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/pci.h>
#include <linux/sysfs.h>

#define DRV_NAME                    "qemu_edu"

#define QEMU_EDU_VENDOR_ID          0x1234
#define QEMU_EDU_DEVICE_ID          0x11e8

#define EDU_REG_IDENTIFICATION      0x00
#define EDU_REG_LIVENESS            0x04
#define EDU_REG_FACTORIAL           0x08
#define EDU_REG_STATUS              0x20
#define EDU_REG_IRQ_STATUS          0x24
#define EDU_REG_IRQ_RAISE           0x60
#define EDU_REG_IRQ_ACK             0x64

#define EDU_STATUS_COMPUTING        BIT(0)
#define EDU_STATUS_IRQ_FACTORIAL    BIT(7)
#define EDU_IRQ_FACTORIAL           BIT(0)

#define EDU_OPERATION_TIMEOUT_MS    2000

struct qemu_edu {
	struct pci_dev *pdev;
	void __iomem *bar0;
	struct mutex operation_lock;
	struct completion factorial_done;
	struct completion any_irq_done;
	atomic_t irq_count;
	u32 last_irq_status;

	bool liveness_valid;
	u32 liveness_input;
	u32 liveness_result;

	bool factorial_valid;
	u32 factorial_input;
	u32 factorial_result;
};

static void qemu_edu_ack_pending_irqs(struct qemu_edu *edu)
{
	u32 status = ioread32(edu->bar0 + EDU_REG_IRQ_STATUS);

	if (status)
		iowrite32(status, edu->bar0 + EDU_REG_IRQ_ACK);
}

static irqreturn_t qemu_edu_irq(int irq, void *data)
{
	struct qemu_edu *edu = data;
	u32 status;

	status = ioread32(edu->bar0 + EDU_REG_IRQ_STATUS);
	if (!status)
		return IRQ_NONE;

	/* INTx is level-triggered: acknowledge the device before returning. */
	iowrite32(status, edu->bar0 + EDU_REG_IRQ_ACK);
	WRITE_ONCE(edu->last_irq_status, status);
	atomic_inc(&edu->irq_count);

	if (status & EDU_IRQ_FACTORIAL)
		complete(&edu->factorial_done);

	complete(&edu->any_irq_done);
	return IRQ_HANDLED;
}

static ssize_t identification_show(struct device *dev,
				   struct device_attribute *attr, char *buf)
{
	struct qemu_edu *edu = dev_get_drvdata(dev);

	return sysfs_emit(buf, "0x%08x\n",
			  ioread32(edu->bar0 + EDU_REG_IDENTIFICATION));
}
static DEVICE_ATTR_RO(identification);

static ssize_t liveness_show(struct device *dev,
			     struct device_attribute *attr, char *buf)
{
	struct qemu_edu *edu = dev_get_drvdata(dev);
	ssize_t len;

	mutex_lock(&edu->operation_lock);
	if (!edu->liveness_valid) {
		len = sysfs_emit(buf, "not-run\n");
	} else {
		len = sysfs_emit(buf,
				 "input=0x%08x result=0x%08x expected=0x%08x\n",
				 edu->liveness_input, edu->liveness_result,
				 ~edu->liveness_input);
	}
	mutex_unlock(&edu->operation_lock);

	return len;
}

static ssize_t liveness_store(struct device *dev,
			      struct device_attribute *attr,
			      const char *buf, size_t count)
{
	struct qemu_edu *edu = dev_get_drvdata(dev);
	u32 value;
	int ret;

	ret = kstrtou32(buf, 0, &value);
	if (ret)
		return ret;

	mutex_lock(&edu->operation_lock);
	iowrite32(value, edu->bar0 + EDU_REG_LIVENESS);
	edu->liveness_input = value;
	edu->liveness_result = ioread32(edu->bar0 + EDU_REG_LIVENESS);
	edu->liveness_valid = true;
	mutex_unlock(&edu->operation_lock);

	return count;
}
static DEVICE_ATTR_RW(liveness);

static ssize_t factorial_show(struct device *dev,
			      struct device_attribute *attr, char *buf)
{
	struct qemu_edu *edu = dev_get_drvdata(dev);
	ssize_t len;

	mutex_lock(&edu->operation_lock);
	if (!edu->factorial_valid)
		len = sysfs_emit(buf, "not-run\n");
	else
		len = sysfs_emit(buf, "%u! = %u\n",
				 edu->factorial_input, edu->factorial_result);
	mutex_unlock(&edu->operation_lock);

	return len;
}

static ssize_t factorial_store(struct device *dev,
			       struct device_attribute *attr,
			       const char *buf, size_t count)
{
	struct qemu_edu *edu = dev_get_drvdata(dev);
	long waited;
	u32 value;
	int ret;

	ret = kstrtou32(buf, 0, &value);
	if (ret)
		return ret;

	/* 12! fits in the EDU device's 32-bit result register; 13! does not. */
	if (value > 12)
		return -ERANGE;

	mutex_lock(&edu->operation_lock);
	edu->factorial_valid = false;

	/* Remove stale state, request an interrupt, then start the operation. */
	iowrite32(0, edu->bar0 + EDU_REG_STATUS);
	qemu_edu_ack_pending_irqs(edu);
	reinit_completion(&edu->factorial_done);
	iowrite32(EDU_STATUS_IRQ_FACTORIAL, edu->bar0 + EDU_REG_STATUS);
	iowrite32(value, edu->bar0 + EDU_REG_FACTORIAL);

	waited = wait_for_completion_interruptible_timeout(
			&edu->factorial_done,
			msecs_to_jiffies(EDU_OPERATION_TIMEOUT_MS));

	/* Stop requesting factorial interrupts, even on timeout or signal. */
	iowrite32(0, edu->bar0 + EDU_REG_STATUS);

	if (waited == 0) {
		ret = -ETIMEDOUT;
		goto out_unlock;
	}
	if (waited < 0) {
		ret = waited;
		goto out_unlock;
	}

	edu->factorial_input = value;
	edu->factorial_result = ioread32(edu->bar0 + EDU_REG_FACTORIAL);
	edu->factorial_valid = true;
	ret = count;

out_unlock:
	mutex_unlock(&edu->operation_lock);
	return ret;
}
static DEVICE_ATTR_RW(factorial);

static ssize_t trigger_irq_store(struct device *dev,
				 struct device_attribute *attr,
				 const char *buf, size_t count)
{
	struct qemu_edu *edu = dev_get_drvdata(dev);
	long waited;
	u32 value;
	int ret;

	ret = kstrtou32(buf, 0, &value);
	if (ret)
		return ret;
	if (!value)
		return -EINVAL;

	mutex_lock(&edu->operation_lock);
	qemu_edu_ack_pending_irqs(edu);
	reinit_completion(&edu->any_irq_done);
	iowrite32(value, edu->bar0 + EDU_REG_IRQ_RAISE);

	waited = wait_for_completion_interruptible_timeout(
			&edu->any_irq_done,
			msecs_to_jiffies(EDU_OPERATION_TIMEOUT_MS));
	if (waited == 0)
		ret = -ETIMEDOUT;
	else if (waited < 0)
		ret = waited;
	else
		ret = count;

	mutex_unlock(&edu->operation_lock);
	return ret;
}
static DEVICE_ATTR_WO(trigger_irq);

static ssize_t irq_count_show(struct device *dev,
			      struct device_attribute *attr, char *buf)
{
	struct qemu_edu *edu = dev_get_drvdata(dev);

	return sysfs_emit(buf, "%d\n", atomic_read(&edu->irq_count));
}
static DEVICE_ATTR_RO(irq_count);

static ssize_t last_irq_status_show(struct device *dev,
				    struct device_attribute *attr, char *buf)
{
	struct qemu_edu *edu = dev_get_drvdata(dev);

	return sysfs_emit(buf, "0x%08x\n",
			  READ_ONCE(edu->last_irq_status));
}
static DEVICE_ATTR_RO(last_irq_status);

static struct attribute *qemu_edu_attrs[] = {
	&dev_attr_identification.attr,
	&dev_attr_liveness.attr,
	&dev_attr_factorial.attr,
	&dev_attr_trigger_irq.attr,
	&dev_attr_irq_count.attr,
	&dev_attr_last_irq_status.attr,
	NULL,
};

static const struct attribute_group qemu_edu_attr_group = {
	.attrs = qemu_edu_attrs,
};

static int qemu_edu_probe(struct pci_dev *pdev,
			  const struct pci_device_id *id)
{
	struct device *dev = &pdev->dev;
	struct qemu_edu *edu;
	u32 identification;
	int ret;

	ret = pcim_enable_device(pdev);
	if (ret)
		return dev_err_probe(dev, ret, "could not enable PCI device\n");

	if (!(pci_resource_flags(pdev, 0) & IORESOURCE_MEM))
		return dev_err_probe(dev, -ENODEV, "BAR0 is not MMIO\n");

	edu = devm_kzalloc(dev, sizeof(*edu), GFP_KERNEL);
	if (!edu)
		return -ENOMEM;

	edu->bar0 = pcim_iomap_region(pdev, 0, DRV_NAME);
	if (IS_ERR(edu->bar0))
		return dev_err_probe(dev, PTR_ERR(edu->bar0),
				     "could not map BAR0\n");

	edu->pdev = pdev;
	mutex_init(&edu->operation_lock);
	init_completion(&edu->factorial_done);
	init_completion(&edu->any_irq_done);
	atomic_set(&edu->irq_count, 0);
	pci_set_drvdata(pdev, edu);

	/* The EDU specification defaults to a 28-bit DMA mask. */
	ret = dma_set_mask_and_coherent(dev, DMA_BIT_MASK(28));
	if (ret)
		return dev_err_probe(dev, ret, "could not set 28-bit DMA mask\n");

	pci_set_master(pdev);
	pci_intx(pdev, 1);

	ret = devm_request_irq(dev, pdev->irq, qemu_edu_irq, IRQF_SHARED,
			       DRV_NAME, edu);
	if (ret)
		return dev_err_probe(dev, ret, "could not request IRQ %u\n",
				     pdev->irq);

	ret = sysfs_create_group(&dev->kobj, &qemu_edu_attr_group);
	if (ret)
		return dev_err_probe(dev, ret, "could not create sysfs files\n");

	identification = ioread32(edu->bar0 + EDU_REG_IDENTIFICATION);
	dev_info(dev,
		 "bound: id=0x%08x BAR0=%pr IRQ=%u; sysfs controls are ready\n",
		 identification, &pdev->resource[0], pdev->irq);

	return 0;
}

static void qemu_edu_remove(struct pci_dev *pdev)
{
	struct qemu_edu *edu = pci_get_drvdata(pdev);

	sysfs_remove_group(&pdev->dev.kobj, &qemu_edu_attr_group);
	iowrite32(0, edu->bar0 + EDU_REG_STATUS);
	qemu_edu_ack_pending_irqs(edu);
	pci_clear_master(pdev);
}

static const struct pci_device_id qemu_edu_ids[] = {
	{ PCI_DEVICE(QEMU_EDU_VENDOR_ID, QEMU_EDU_DEVICE_ID) },
	{ }
};
MODULE_DEVICE_TABLE(pci, qemu_edu_ids);

static struct pci_driver qemu_edu_driver = {
	.name = DRV_NAME,
	.id_table = qemu_edu_ids,
	.probe = qemu_edu_probe,
	.remove = qemu_edu_remove,
};
module_pci_driver(qemu_edu_driver);

MODULE_AUTHOR("Yocto QEMU EDU learning project");
MODULE_DESCRIPTION("Learning driver for the QEMU EDU PCI device");
MODULE_LICENSE("GPL");
