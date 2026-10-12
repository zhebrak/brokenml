"""The image guard: a container refuses to run a task rendered against other image sources (harness.imagelock)."""

from pathlib import Path

from harness import imagelock

LOCK = """# benchmark-canary GUID 00000000-0000-0000-0000-000000000000
# The images used here and a hash of the sources each is built from (bench.provenance).
harness bench/harness:dev 7c970e0dc60da0c1
runtime bench/runtime:dev e514e4675f3b2d07
"""


def test_parse_skips_comments_and_keeps_tag_and_hash():
    assert imagelock.parse(LOCK) == {"harness": ("bench/harness:dev", "7c970e0dc60da0c1"),
                                     "runtime": ("bench/runtime:dev", "e514e4675f3b2d07")}  # fmt: skip
    assert imagelock.parse("") == {} and imagelock.parse("harness only-two-fields\n") == {}


def test_matching_images_pass_and_unpinned_or_absent_roles_are_not_compared():
    lock = imagelock.parse(LOCK)
    assert imagelock.mismatches(lock, {"harness": "7c970e0dc60da0c1", "runtime": "e514e4675f3b2d07"}) == []
    assert imagelock.mismatches(lock, {"harness": "7c970e0dc60da0c1"}) == []  # a node carries no harness VERSION
    assert imagelock.mismatches({}, {"harness": "anything"}) == []  # a task that pins nothing


def test_a_rebuilt_image_is_named_with_both_hashes():
    lock = imagelock.parse(LOCK)
    (line,) = imagelock.mismatches(lock, {"harness": "9d6a0ac96baf11ed", "runtime": "e514e4675f3b2d07"})
    assert line.startswith("harness: ") and "9d6a0ac96baf11ed" in line and "7c970e0dc60da0c1" in line
    assert "(bench/harness:dev)" in line


def test_running_reads_only_the_version_files_present(tmp_path: Path):
    (tmp_path / "ocb").mkdir()
    (tmp_path / "ocb" / "VERSION").write_text("e514e4675f3b2d07\n")
    files = {"runtime": tmp_path / "ocb" / "VERSION", "harness": tmp_path / "harness" / "VERSION"}
    assert imagelock.running(files) == {"runtime": "e514e4675f3b2d07"}


def test_expected_from_env_covers_containers_without_the_lock():
    env = {"OCB_EXPECT_RUNTIME": "e514e4675f3b2d07", "OTHER": "x"}
    assert imagelock.expected_from_env(env) == {"runtime": ("", "e514e4675f3b2d07")}
    (line,) = imagelock.mismatches(imagelock.expected_from_env(env), {"runtime": "deadbeefdeadbeef"})
    assert line.endswith("rendered against e514e4675f3b2d07")  # no tag to name
