import hashlib
import pathlib
import unittest


OPENZERO_ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLER = OPENZERO_ROOT / "install.sh"
CHECKSUM = OPENZERO_ROOT / "install.sh.sha256"
UPDATER = OPENZERO_ROOT / "update.sh"


class PublicInstallerChecksumTests(unittest.TestCase):
    def test_published_checksum_matches_installer(self):
        fields = CHECKSUM.read_text(encoding="utf-8").strip().split()
        self.assertEqual(fields, [hashlib.sha256(INSTALLER.read_bytes()).hexdigest(), "install.sh"])

    def test_updater_verifies_the_published_checksum(self):
        source = UPDATER.read_text(encoding="utf-8")
        self.assertIn("install.sh.sha256", source)
        self.assertIn("sha256sum -c", source)


if __name__ == "__main__":
    unittest.main()
