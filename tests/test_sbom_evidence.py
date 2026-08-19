# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sbom_evidence", ROOT / "scripts/sbom_evidence.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample_evidence(lab_id: str = "pci-x86-64") -> dict:
    identity = MODULE.LAB_IDENTITIES[lab_id]
    packages = [
        {"name": name, "version": "1.0", "declared_license": license_expression}
        for name, license_expression in sorted(identity["packages"].items())
    ]
    return {
        "schema_version": 1,
        "kind": MODULE.KIND,
        "project": {
            "name": MODULE.PROJECT_NAME,
            "version": "0.7.0-dev",
            "revision": "1" * 40,
            "dirty": False,
        },
        "inputs": {
            "source_lock_sha256": "2" * 64,
            "openembedded_core_commit": "3" * 40,
            "lab_index_sha256": "4" * 64,
            "lab_manifest_sha256": "5" * 64,
            "yocto_version": "6.0.2",
            "yocto_series": "wrynose",
        },
        "lab": {
            "id": lab_id,
            "machine": identity["machine"],
            "image": identity["image"],
            "evidence_profile": MODULE.EVIDENCE_PROFILE,
        },
        "generator": {
            "name": "openembedded-create-spdx",
            "spdx_version": MODULE.SPDX_VERSION,
            "profiles": list(MODULE.PROFILES),
            "settings": dict(MODULE.EXPECTED_SETTINGS),
        },
        "source_sbom": {
            "basename": "qemu-edu-image-machine.rootfs.spdx.json",
            "sha256": "6" * 64,
            "size_bytes": 4096,
            "document_count": 1,
            "sbom_count": 1,
            "root_element_count": 2,
            "unresolved_id_count": 0,
            "installed_package_count": 20,
            "artifact_count": 1,
        },
        "packages": packages,
        "artifacts": [
            {"basename": "qemu-edu-image.ext4", "sha256": "7" * 64, "size_bytes": 8192}
        ],
        "checks": [
            {"id": check_id, "status": "passed"} for check_id in MODULE.CHECK_IDS
        ],
        "task_exit_code": 0,
        "result": "passed",
    }


class Element:
    pass


class Package(Element):
    def __init__(self, name: str, version: str = "1.0", purpose: str = "install") -> None:
        self.name = name
        self.software_packageVersion = version
        self.software_primaryPurpose = purpose


class File(Element):
    def __init__(self, name: str, digest: str) -> None:
        self.name = name
        self.verifiedUsing = [Hash(HashAlgorithm.sha256, digest)]


class Sbom(Element):
    def __init__(self, roots: list[Element]) -> None:
        self.rootElement = roots
        self.software_sbomType = [SbomType.build]


class Document(Element):
    def __init__(self, sbom: Sbom) -> None:
        self.rootElement = [sbom]
        self.import_ = []
        self.creationInfo = types.SimpleNamespace(specVersion="3.0.1")
        self.profileConformance = [
            getattr(ProfileIdentifierType, profile) for profile in MODULE.PROFILES
        ]


class Build(Element):
    def __init__(self, name: str) -> None:
        self.name = name
        self.build_buildType = MODULE.ROOTFS_BUILD_TYPE


class LicenseExpression(Element):
    def __init__(self, expression: str) -> None:
        self.simplelicensing_licenseExpression = expression


class Hash:
    def __init__(self, algorithm: str, value: str) -> None:
        self.algorithm = algorithm
        self.hashValue = value


class HashAlgorithm:
    sha256 = "sha256"


class SbomType:
    build = "build"


class RelationshipType:
    hasInput = "hasInput"
    hasOutput = "hasOutput"
    hasDeclaredLicense = "hasDeclaredLicense"


class LifecycleScopeType:
    build = "build"


class SoftwarePurpose:
    archive = "archive"
    install = "install"


class ProfileIdentifierType:
    build = "build"
    core = "core"
    security = "security"
    simpleLicensing = "simpleLicensing"
    software = "software"


class Relationship(Element):
    def __init__(self, from_: Element, relationship_type: str, to: list[Element]) -> None:
        self.from_ = from_
        self.relationshipType = relationship_type
        self.to = to


class LifecycleScopedRelationship(Relationship):
    def __init__(
        self, from_: Element, relationship_type: str, to: list[Element]
    ) -> None:
        super().__init__(from_, relationship_type, to)
        self.scope = LifecycleScopeType.build


FAKE_SPDX = types.SimpleNamespace(
    SpdxDocument=Document,
    software_Sbom=Sbom,
    software_Package=Package,
    software_File=File,
    build_Build=Build,
    Relationship=Relationship,
    LifecycleScopedRelationship=LifecycleScopedRelationship,
    simplelicensing_LicenseExpression=LicenseExpression,
    Hash=Hash,
    HashAlgorithm=HashAlgorithm,
    software_SbomType=SbomType,
    RelationshipType=RelationshipType,
    LifecycleScopeType=LifecycleScopeType,
    software_SoftwarePurpose=SoftwarePurpose,
    ProfileIdentifierType=ProfileIdentifierType,
)


class ObjectSet:
    def __init__(self, objects: list[Element], missing_ids: set[str] | None = None) -> None:
        self.objects = objects
        self.missing_ids = missing_ids or set()

    def foreach_type(self, object_type):
        return (item for item in self.objects if isinstance(item, object_type))


def graph_fixture(root: Path, lab_id: str = "pci-x86-64") -> tuple[ObjectSet, Path]:
    identity = MODULE.LAB_IDENTITIES[lab_id]
    artifact_path = root / "qemu-edu-image.ext4"
    artifact_path.write_bytes(b"image-bytes")
    artifact_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    artifact = File(artifact_path.name, artifact_digest)
    root_package = Package(identity["image"], purpose=SoftwarePurpose.archive)
    sbom = Sbom([root_package, artifact])
    document = Document(sbom)
    build = Build(f"{identity['image']}:do_create_rootfs_spdx:rootfs")
    installed = [Package(name) for name in sorted(identity["packages"])]
    relationships: list[Element] = [
        LifecycleScopedRelationship(build, RelationshipType.hasOutput, [root_package]),
        LifecycleScopedRelationship(build, RelationshipType.hasInput, installed),
    ]
    for package in installed:
        relationships.append(
            Relationship(
                package,
                RelationshipType.hasDeclaredLicense,
                [LicenseExpression(identity["packages"][package.name])],
            )
        )
    return ObjectSet([document, sbom, build, *installed, artifact, *relationships]), root


class SbomEvidenceTests(unittest.TestCase):
    def test_semantic_validator_accepts_both_closed_lab_profiles(self) -> None:
        for lab_id in MODULE.LAB_IDENTITIES:
            with self.subTest(lab_id=lab_id):
                MODULE.validate_evidence(sample_evidence(lab_id), require_pass=True)

    def test_boolean_integer_aliases_and_dirty_pass_are_rejected(self) -> None:
        evidence = sample_evidence()
        evidence["source_sbom"]["size_bytes"] = True
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "size_bytes"):
            MODULE.validate_evidence(evidence)

        evidence = sample_evidence()
        evidence["project"]["dirty"] = True
        MODULE.validate_evidence(evidence)
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "clean project tree"):
            MODULE.validate_evidence(evidence, require_pass=True)

        evidence = sample_evidence()
        evidence["project"]["version"] = "0.7.0+" + "a" * 123
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "128 characters"):
            MODULE.validate_evidence(evidence)

        evidence = sample_evidence()
        evidence["inputs"]["yocto_version"] = "6/0/2"
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "unsupported"):
            MODULE.validate_evidence(evidence)

    def test_package_identity_license_and_order_are_closed(self) -> None:
        evidence = sample_evidence()
        evidence["packages"][0]["declared_license"] = "MIT"
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "declared license"):
            MODULE.validate_evidence(evidence)

        evidence = sample_evidence()
        evidence["packages"].reverse()
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "out of order"):
            MODULE.validate_evidence(evidence)

    def test_counts_artifacts_checks_and_revision_are_correlated(self) -> None:
        evidence = sample_evidence()
        evidence["source_sbom"]["root_element_count"] = 3
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "counts are inconsistent"):
            MODULE.validate_evidence(evidence)

        evidence = sample_evidence()
        evidence["checks"][0], evidence["checks"][1] = (
            evidence["checks"][1],
            evidence["checks"][0],
        )
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "did not pass exactly"):
            MODULE.validate_evidence(evidence)

        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "required"):
            MODULE.validate_evidence(sample_evidence(), expected_revision="8" * 40)

    def test_current_input_binding_rejects_stale_locked_identity(self) -> None:
        evidence = sample_evidence()
        identity = MODULE.LAB_IDENTITIES["pci-x86-64"]
        manifest = {
            "build": {
                "machine": identity["machine"],
                "targets": [identity["image"]],
            }
        }
        selected = (
            manifest,
            "pci-x86-64",
            evidence["inputs"]["lab_index_sha256"],
            evidence["inputs"]["lab_manifest_sha256"],
            identity["packages"],
            [],
        )
        source = (
            {
                "release": {
                    "version": evidence["inputs"]["yocto_version"],
                    "series": evidence["inputs"]["yocto_series"],
                }
            },
            evidence["inputs"]["source_lock_sha256"],
            {"commit": evidence["inputs"]["openembedded_core_commit"]},
        )
        with (
            mock.patch.object(MODULE, "selected_contract", return_value=selected),
            mock.patch.object(MODULE, "source_authority", return_value=source),
        ):
            MODULE.validate_evidence(evidence, current_repo=ROOT)
            stale = copy.deepcopy(evidence)
            stale["inputs"]["source_lock_sha256"] = "9" * 64
            with self.assertRaisesRegex(MODULE.SbomEvidenceError, "not match current"):
                MODULE.validate_evidence(stale, current_repo=ROOT)

    def test_exact_generator_settings_fail_closed(self) -> None:
        arguments = [f"{name}={value}" for name, value in MODULE.EXPECTED_SETTINGS.items()]
        self.assertEqual(MODULE.EXPECTED_SETTINGS, MODULE.parse_settings(arguments))
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "incomplete"):
            MODULE.parse_settings(arguments[:-1])
        changed = list(arguments)
        changed[0] += "supplier"
        with self.assertRaisesRegex(MODULE.SbomEvidenceError, "expected"):
            MODULE.parse_settings(changed)

    def test_evidence_reader_rejects_duplicate_keys_and_unsafe_strings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            path.write_bytes(b'{"schema_version":1,"schema_version":1}')
            with self.assertRaisesRegex(MODULE.SbomEvidenceError, "duplicate JSON key"):
                MODULE.read_evidence(path)

            path.write_bytes(b'{"value":"\\ud800"}')
            with self.assertRaisesRegex(MODULE.SbomEvidenceError, "surrogate"):
                MODULE.read_evidence(path)

            path.write_bytes(b'{"value":"line\\nfeed"}')
            with self.assertRaisesRegex(MODULE.SbomEvidenceError, "control character"):
                MODULE.read_evidence(path)

    def test_locked_model_import_does_not_write_into_the_source_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model_root = root / "layers/openembedded-core/meta/lib/oe/spdx30"
            model_root.mkdir(parents=True)
            (model_root.parent / "__init__.py").write_text("", encoding="utf-8")
            (model_root / "__init__.py").write_text(
                "MODEL_MARKER = 'locked'\n", encoding="utf-8"
            )
            source = {"path": "layers/openembedded-core"}
            try:
                loaded = MODULE.load_spdx_model(root, source)
                self.assertEqual("locked", loaded.MODEL_MARKER)
                self.assertTrue(sys.dont_write_bytecode)
                self.assertFalse(any(root.rglob("*.pyc")))
                self.assertFalse(any(root.rglob("__pycache__")))
            finally:
                sys.modules.pop("oe.spdx30", None)
                sys.modules.pop("oe", None)
                sys.path.remove(str(root / "layers/openembedded-core/meta/lib"))

    def test_graph_analysis_proves_packages_licenses_and_artifact_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            objset, deploy_dir = graph_fixture(root)
            identity = MODULE.LAB_IDENTITIES["pci-x86-64"]
            analysis = MODULE.analyze_graph(
                spdx=FAKE_SPDX,
                objset=objset,
                deploy_dir=deploy_dir,
                image=identity["image"],
                required_packages=identity["packages"],
                forbidden_packages=list(
                    MODULE.LAB_IDENTITIES["platform-arm64"]["packages"]
                ),
            )
            self.assertEqual(3, len(analysis["packages"]))
            self.assertEqual(1, len(analysis["artifacts"]))
            self.assertEqual(3, analysis["installed_package_count"])

    def test_graph_analysis_rejects_unresolved_ids_and_artifact_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            objset, deploy_dir = graph_fixture(root)
            objset.missing_ids.add("https://example.invalid/missing")
            identity = MODULE.LAB_IDENTITIES["pci-x86-64"]
            with self.assertRaisesRegex(MODULE.SbomEvidenceError, "unresolved"):
                MODULE.analyze_graph(
                    spdx=FAKE_SPDX,
                    objset=objset,
                    deploy_dir=deploy_dir,
                    image=identity["image"],
                    required_packages=identity["packages"],
                    forbidden_packages=[],
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            objset, deploy_dir = graph_fixture(root)
            (root / "qemu-edu-image.ext4").write_bytes(b"tampered")
            identity = MODULE.LAB_IDENTITIES["pci-x86-64"]
            with self.assertRaisesRegex(MODULE.SbomEvidenceError, "SHA-256 mismatch"):
                MODULE.analyze_graph(
                    spdx=FAKE_SPDX,
                    objset=objset,
                    deploy_dir=deploy_dir,
                    image=identity["image"],
                    required_packages=identity["packages"],
                    forbidden_packages=[],
                )

    def test_graph_analysis_rejects_wrong_purposes_type_scope_and_forbidden_input(self) -> None:
        identity = MODULE.LAB_IDENTITIES["pci-x86-64"]
        cases = ("root-purpose", "build-type", "package-purpose", "input-scope")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                objset, deploy_dir = graph_fixture(Path(temporary))
                sbom = next(item for item in objset.objects if isinstance(item, Sbom))
                root_package = next(
                    item
                    for item in sbom.rootElement
                    if isinstance(item, Package) and item.name == identity["image"]
                )
                build = next(item for item in objset.objects if isinstance(item, Build))
                input_relation = next(
                    item
                    for item in objset.objects
                    if isinstance(item, LifecycleScopedRelationship)
                    and item.relationshipType == RelationshipType.hasInput
                )
                if case == "root-purpose":
                    root_package.software_primaryPurpose = SoftwarePurpose.install
                    expected = "archive purpose"
                elif case == "build-type":
                    build.build_buildType = "https://example.invalid/build"
                    expected = "build type"
                elif case == "package-purpose":
                    input_relation.to[0].software_primaryPurpose = SoftwarePurpose.archive
                    expected = "install purpose"
                else:
                    input_relation.scope = "runtime"
                    expected = "lifecycle scope"
                with self.assertRaisesRegex(MODULE.SbomEvidenceError, expected):
                    MODULE.analyze_graph(
                        spdx=FAKE_SPDX,
                        objset=objset,
                        deploy_dir=deploy_dir,
                        image=identity["image"],
                        required_packages=identity["packages"],
                        forbidden_packages=[],
                    )

        with tempfile.TemporaryDirectory() as temporary:
            objset, deploy_dir = graph_fixture(Path(temporary))
            input_relation = next(
                item
                for item in objset.objects
                if isinstance(item, LifecycleScopedRelationship)
                and item.relationshipType == RelationshipType.hasInput
            )
            input_relation.to.append(Package("qemu-edu-platform-tools"))
            with self.assertRaisesRegex(MODULE.SbomEvidenceError, "forbidden"):
                MODULE.analyze_graph(
                    spdx=FAKE_SPDX,
                    objset=objset,
                    deploy_dir=deploy_dir,
                    image=identity["image"],
                    required_packages=identity["packages"],
                    forbidden_packages=["qemu-edu-platform-tools"],
                )

    def test_artifact_and_stable_sbom_links_cannot_escape_deployment(self) -> None:
        identity = MODULE.LAB_IDENTITIES["pci-x86-64"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deploy = root / "deploy"
            deploy.mkdir()
            objset, _ = graph_fixture(deploy)
            artifact = deploy / "qemu-edu-image.ext4"
            outside_artifact = root / "outside.ext4"
            outside_artifact.write_bytes(artifact.read_bytes())
            artifact.unlink()
            try:
                os.symlink(outside_artifact, artifact)
            except OSError as exc:
                self.skipTest(f"host cannot create a symbolic link: {exc}")
            with self.assertRaisesRegex(MODULE.SbomEvidenceError, "regular deployed"):
                MODULE.analyze_graph(
                    spdx=FAKE_SPDX,
                    objset=objset,
                    deploy_dir=deploy,
                    image=identity["image"],
                    required_packages=identity["packages"],
                    forbidden_packages=[],
                )

            inside_sbom = deploy / "image-real.spdx.json"
            inside_sbom.write_text("{}\n", encoding="utf-8")
            stable = deploy / "image-link.spdx.json"
            os.symlink(inside_sbom.name, stable)
            self.assertEqual(
                inside_sbom.resolve(), MODULE.resolve_sbom_path(deploy, "image-link")[0]
            )
            stable.unlink()
            outside_sbom = root / "outside.spdx.json"
            outside_sbom.write_text("{}\n", encoding="utf-8")
            os.symlink(outside_sbom, stable)
            with self.assertRaisesRegex(MODULE.SbomEvidenceError, "escapes"):
                MODULE.resolve_sbom_path(deploy, "image-link")

    def test_evidence_schema_is_closed(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/qemu-edu-sbom-evidence-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertEqual(128, schema["properties"]["artifacts"]["maxItems"])


if __name__ == "__main__":
    unittest.main()
