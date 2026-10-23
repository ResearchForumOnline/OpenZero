"""Offline synthetic transport, integrity, reassembly and path-boundary tests."""
import contextlib
import copy
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.request

import download_model_archive as tool


def fixture(chunks=(b"synthetic-first", b"synthetic-second")):
    entry = {"name": "model.zip", "bytes": sum(map(len, chunks)),
             "sha256": hashlib.sha256(b"".join(chunks)).hexdigest(), "parts": []}
    bodies = {}
    for index, data in enumerate(chunks, 1):
        name = f"synthetic.part{index:03d}"
        url = tool.RELEASE_PREFIX + name
        entry["parts"].append({"name": name, "url": url, "bytes": len(data),
                               "sha256": hashlib.sha256(data).hexdigest()})
        bodies[url] = data
    return entry, bodies


class Response(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data)
        self.url, self.read_sizes = url, []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)

    def geturl(self):
        return self.url


class ModelArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dest = self.root / "restored"
        self.entry, self.bodies = fixture()
        self.calls, self.responses = [], []

    def tearDown(self):
        self.temp.cleanup()

    def transport(self, url):
        self.calls.append(url)
        response = Response(self.bodies[url], url)
        self.responses.append(response)
        return response

    def restore(self, entry=None, transport=None):
        return tool.restore_file(entry or self.entry, self.dest, transport or self.transport)

    def no_outputs(self):
        self.assertFalse((self.dest / self.entry["name"]).exists())
        self.assertFalse((self.dest / (self.entry["name"] + ".partial")).exists())

    def manifest(self, entry=None):
        return {"schema_version": 1, "id": "openzero-model-archive-mirror",
                "files": [entry or self.entry]}

    def link(self, path, target, directory=False):
        try:
            path.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not permit symlink creation for this test account")

    def test_three_parts_and_multiple_chunks_reconstruct_original(self):
        parts = (b"A" * (tool.CHUNK_BYTES + 37), b"BC" * 100, b"synthetic-end")
        self.entry, self.bodies = fixture(parts)
        target = self.restore()
        self.assertEqual(target.read_bytes(), b"".join(parts))
        self.assertEqual(self.calls, [p["url"] for p in self.entry["parts"]])
        self.assertGreaterEqual(len(self.responses[0].read_sizes), 3)
        self.assertTrue(all(n == tool.CHUNK_BYTES for r in self.responses for n in r.read_sizes))
        self.assertFalse(target.with_name(target.name + ".partial").exists())

    def test_altered_same_length_part_cleans_partial(self):
        url = self.entry["parts"][0]["url"]
        self.bodies[url] = b"X" * len(self.bodies[url])
        with self.assertRaisesRegex(ValueError, "part length or SHA-256"):
            self.restore()
        self.no_outputs()

    def test_truncated_part_cleans_partial(self):
        url = self.entry["parts"][0]["url"]
        self.bodies[url] = self.bodies[url][:-1]
        with self.assertRaisesRegex(ValueError, "part length or SHA-256"):
            self.restore()
        self.no_outputs()

    def test_oversize_part_cleans_partial(self):
        self.bodies[self.entry["parts"][0]["url"]] += b"extra"
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.restore()
        self.no_outputs()

    def test_correct_parts_but_wrong_whole_hash_cleans_partial(self):
        self.entry["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Complete model archive"):
            self.restore()
        self.assertEqual(len(self.calls), 2)
        self.no_outputs()

    def test_network_open_failure_after_first_part_cleans_partial(self):
        def transport(url):
            if url == self.entry["parts"][1]["url"]:
                raise OSError("synthetic outage")
            return self.transport(url)
        with self.assertRaisesRegex(OSError, "Transport failed"):
            self.restore(transport=transport)
        self.no_outputs()

    def test_network_read_failure_cleans_partial(self):
        class Broken(Response):
            def read(self, size=-1):
                raise OSError("synthetic read failure")
        with self.assertRaisesRegex(OSError, "synthetic read failure"):
            self.restore(transport=lambda u: Broken(b"", u))
        self.no_outputs()

    def test_interrupt_cleans_owned_partial(self):
        def transport(url):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.restore(transport=transport)
        self.no_outputs()

    def test_existing_target_preserved_without_network(self):
        self.dest.mkdir()
        target = self.dest / self.entry["name"]
        target.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            self.restore()
        self.assertEqual(target.read_bytes(), b"existing")
        self.assertEqual(self.calls, [])

    def test_existing_partial_preserved_without_network(self):
        self.dest.mkdir()
        partial = self.dest / (self.entry["name"] + ".partial")
        partial.write_bytes(b"prior interrupted download")
        with self.assertRaises(FileExistsError):
            self.restore()
        self.assertEqual(partial.read_bytes(), b"prior interrupted download")
        self.assertEqual(self.calls, [])

    def test_concurrent_target_never_overwritten(self):
        def transport(url):
            target = self.dest / self.entry["name"]
            if not target.exists():
                target.write_bytes(b"concurrent target")
            return self.transport(url)
        with self.assertRaises(FileExistsError):
            self.restore(transport=transport)
        self.assertEqual((self.dest / self.entry["name"]).read_bytes(), b"concurrent target")
        self.assertFalse((self.dest / (self.entry["name"] + ".partial")).exists())

    def test_target_symlink_preserves_outside_file(self):
        self.dest.mkdir()
        outside = self.root / "outside"
        outside.write_bytes(b"outside")
        self.link(self.dest / self.entry["name"], outside)
        with self.assertRaises(FileExistsError):
            self.restore()
        self.assertEqual(outside.read_bytes(), b"outside")
        self.assertEqual(self.calls, [])

    def test_partial_symlink_preserves_outside_file(self):
        self.dest.mkdir()
        outside = self.root / "outside"
        outside.write_bytes(b"outside")
        self.link(self.dest / (self.entry["name"] + ".partial"), outside)
        with self.assertRaises(FileExistsError):
            self.restore()
        self.assertEqual(outside.read_bytes(), b"outside")

    def test_destination_symlink_cannot_write_outside(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.link(self.dest, outside, True)
        with self.assertRaisesRegex(ValueError, "ordinary directories"):
            self.restore()
        self.assertEqual(list(outside.iterdir()), [])

    def test_ancestor_symlink_cannot_write_outside(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.link(self.root / "linked", outside, True)
        self.dest = self.root / "linked" / "new-child"
        with self.assertRaisesRegex(ValueError, "ordinary directories"):
            self.restore()
        self.assertFalse((outside / "new-child").exists())

    def test_unsafe_names_rejected_before_any_io(self):
        for name in ("../outside", "a/b", "a\\b", "C:outside", "/outside", "CON", "NUL.txt", "trailing.", "%2foutside"):
            entry = copy.deepcopy(self.entry)
            entry["name"] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.restore(entry)
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.calls, [])

    def test_exact_release_url_required(self):
        for url in ("http://github.com/asset", "https://github.com.evil.example/asset",
                    tool.RELEASE_PREFIX.replace("model-archive-mirror-2026.10.23", "other-release") + "x",
                    self.entry["parts"][0]["url"] + "?alternate=1", "https://evil.example/file"):
            entry = copy.deepcopy(self.entry)
            entry["parts"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.restore(entry)
        self.assertEqual(self.calls, [])

    def test_size_digest_and_part_sum_validation(self):
        for key, value in (("bytes", True), ("bytes", -1), ("sha256", "invalid"),
                           ("bytes", self.entry["bytes"] + 1)):
            entry = copy.deepcopy(self.entry)
            entry[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                tool.validate_manifest(self.manifest(entry))

    def test_case_insensitive_duplicate_and_partial_collision(self):
        entry = copy.deepcopy(self.entry)
        entry["name"] = entry["name"].upper()
        document = self.manifest()
        document["files"].append(entry)
        with self.assertRaises(ValueError):
            tool.validate_manifest(document)
        entry["name"] = self.entry["name"] + ".partial"
        for part in entry["parts"]:
            part["name"] = "other-" + part["name"]
            part["url"] = tool.RELEASE_PREFIX + part["name"]
        with self.assertRaisesRegex(ValueError, "conflicting"):
            tool.validate_manifest(document)

    def test_response_host_validation_and_cleanup(self):
        with self.assertRaisesRegex(ValueError, "Response URL"):
            self.restore(transport=lambda _: Response(b"", "https://evil.example/file"))
        self.no_outputs()

    def test_redirect_handler_blocks_foreign_http_and_credentials(self):
        handler = tool.ReleaseRedirectHandler()
        request = urllib.request.Request(self.entry["parts"][0]["url"])
        for url in ("http://release-assets.githubusercontent.com/file", "https://evil.example/file",
                    "https://user:password@release-assets.githubusercontent.com/file"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "Found", {}, url)
        self.assertTrue(tool.approved_transport_url("https://release-assets.githubusercontent.com/file?signature=synthetic"))

    def test_cli_list_selects_exact_file_without_network(self):
        capture = io.StringIO()
        with mock.patch.object(tool, "read_manifest", return_value=[self.entry]), contextlib.redirect_stdout(capture):
            self.assertEqual(tool.main(["--list", "--file", self.entry["name"]]), 0)
        self.assertIn(self.entry["name"], capture.getvalue())
        self.assertIn("2 part(s)", capture.getvalue())
        self.assertFalse(self.dest.exists())

    def test_cli_preflights_targets_before_network(self):
        self.dest.mkdir()
        (self.dest / self.entry["name"]).write_bytes(b"preserve")
        with mock.patch.object(tool, "read_manifest", return_value=[self.entry]), \
                mock.patch.object(tool, "restore_file") as download, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(["--destination", str(self.dest)]), 1)
            download.assert_not_called()

    def test_cli_unknown_filename_does_not_create_destination(self):
        with mock.patch.object(tool, "read_manifest", return_value=[self.entry]), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(["--destination", str(self.dest), "--file", "unknown.zip"]), 1)
        self.assertFalse(self.dest.exists())


    def test_pinned_manifest_identity_and_schema_required(self):
        for field, value in (("id", "aadr-v14-public-reference"),
                             ("id", "other-model-release"),
                             ("schema_version", True), ("schema_version", 2)):
            document = self.manifest()
            document[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                tool.validate_manifest(document)
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.calls, [])

    def test_eight_parts_restore_two_whole_zip_archives_without_extracting(self):
        import zipfile
        entries, self.bodies = [], {}
        expected = {}
        for index in range(2):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("synthetic.txt", f"synthetic archive {index} " * 100)
            raw = buffer.getvalue()
            cuts = [len(raw) * n // 4 for n in range(5)]
            chunks = tuple(raw[cuts[n]:cuts[n + 1]] for n in range(4))
            entry, bodies = fixture(chunks)
            entry["name"] = f"synthetic-model-{index}.zip"
            for part in entry["parts"]:
                old_url = part["url"]
                part["name"] = f"model-{index}-" + part["name"]
                part["url"] = tool.RELEASE_PREFIX + part["name"]
                self.bodies[part["url"]] = bodies[old_url]
            entries.append(entry)
            expected[entry["name"]] = raw
        document = {"schema_version": 1, "id": "openzero-model-archive-mirror",
                    "files": entries}
        for entry in tool.validate_manifest(document):
            target = self.restore(entry)
            self.assertEqual(target.read_bytes(), expected[entry["name"]])
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), entry["sha256"])
        self.assertEqual(len(self.calls), 8)
        self.assertEqual({p.name for p in self.dest.iterdir()}, set(expected))
        self.assertFalse((self.dest / "synthetic.txt").exists())

    def test_reordered_valid_parts_fail_whole_archive_hash(self):
        self.entry["parts"].reverse()
        with self.assertRaisesRegex(ValueError, "Complete model archive"):
            self.restore()
        self.assertEqual(len(self.calls), 2)
        self.no_outputs()

    def test_duplicate_part_names_across_archives_rejected(self):
        document = self.manifest()
        other = copy.deepcopy(self.entry)
        other["name"] = "another-model.zip"
        document["files"].append(other)
        with self.assertRaisesRegex(ValueError, "Duplicate release asset"):
            tool.validate_manifest(document)
        self.assertFalse(self.dest.exists())

    def test_read_repository_manifest_validates_pinned_identity(self):
        import json
        path = self.root / "manifest.json"
        path.write_text(json.dumps(self.manifest()), encoding="utf-8")
        self.assertEqual(tool.read_manifest(path), [self.entry])
        wrong = self.manifest()
        wrong["id"] = "another-release"
        path.write_text(json.dumps(wrong), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unsupported model archive"):
            tool.read_manifest(path)

    def test_anonymous_transport_bypasses_stale_cache_without_changing_pinned_url(self):
        url = self.entry["parts"][0]["url"]
        with mock.patch.object(tool.urllib.request, "build_opener") as factory:
            tool.open_release_part(url)
        request = factory.return_value.open.call_args.args[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(request.full_url, url)
        self.assertEqual(headers["cache-control"], "no-cache")
        self.assertEqual(headers["accept-encoding"], "identity")
        self.assertNotIn("authorization", headers)
        self.assertNotIn("cookie", headers)
        self.assertEqual(factory.return_value.open.call_args.kwargs["timeout"], 60)


if __name__ == "__main__":
    unittest.main()
