import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.textutil import slugify, truncate, split_frontmatter


def test_hello_world():
    assert slugify("Hello, World!") == "hello-world"


def test_underscores_and_spaces():
    assert slugify("  A__B  ") == "a-b"


def test_accented_characters():
    assert slugify("café & crème") == "caf-cr-me"


def test_empty_string():
    assert slugify("") == ""


def test_lowercases_output():
    assert slugify("UPPER") == "upper"


def test_single_word_no_special_chars():
    assert slugify("hello") == "hello"


def test_multiple_consecutive_non_alphanumeric_collapsed():
    assert slugify("a---b") == "a-b"


def test_no_leading_hyphen():
    result = slugify("!hello")
    assert not result.startswith("-")


def test_no_trailing_hyphen():
    result = slugify("hello!")
    assert not result.endswith("-")


def test_pure_non_alphanumeric():
    assert slugify("!!!") == ""


def test_numbers_preserved():
    assert slugify("version 2.0") == "version-2-0"


def test_return_type_is_str():
    assert isinstance(slugify("test"), str)
    assert isinstance(slugify(""), str)


# truncate() tests

def test_truncate_short_string_unchanged():
    # len("hello") == 5 <= 10, return as-is
    assert truncate("hello", 10) == "hello"


def test_truncate_exact_length_unchanged():
    # len("abc") == 3 == n, return as-is
    assert truncate("abc", 3) == "abc"


def test_truncate_long_string_with_default_suffix():
    # len("hello world") == 11 > 8, result must be exactly 8 chars
    result = truncate("hello world", 8)
    assert result == "hello w…"
    assert len(result) == 8


def test_truncate_result_exactly_n_chars():
    result = truncate("abcdefghij", 5)
    assert len(result) == 5
    assert result == "abcd…"


def test_truncate_custom_suffix():
    result = truncate("hello world", 8, suffix="...")
    assert result == "hello..."
    assert len(result) == 8


def test_truncate_empty_suffix():
    result = truncate("hello world", 5, suffix="")
    assert result == "hello"
    assert len(result) == 5


def test_truncate_returns_str():
    assert isinstance(truncate("hello", 10), str)
    assert isinstance(truncate("hello world", 5), str)


def test_truncate_n_equals_len_text_unchanged():
    text = "exactly"
    assert truncate(text, len(text)) == text


def test_truncate_n_one_greater_than_len_unchanged():
    assert truncate("hi", 3) == "hi"


def test_truncate_single_char_suffix_boundary():
    # "abcd" len 4, n=3, suffix default "…" len 1 → "ab…"
    result = truncate("abcd", 3)
    assert result == "ab…"
    assert len(result) == 3


# split_frontmatter() tests — parses our controlled YAML-ish frontmatter (stdlib only)

def test_split_no_frontmatter_returns_empty_meta_and_full_body():
    text = "# Just a heading\n\nNo frontmatter here.\n"
    meta, body = split_frontmatter(text)
    assert meta == {}
    assert body == text


def test_split_simple_key_value():
    text = "---\ntype: task\n---\n# Body\n"
    meta, body = split_frontmatter(text)
    assert meta["type"] == "task"


def test_split_body_preserved_exactly_after_closing_fence():
    text = "---\ntype: task\n---\n# Body line\n\nsecond para\n"
    meta, body = split_frontmatter(text)
    assert body == "# Body line\n\nsecond para\n"


def test_split_strips_double_quotes_from_value():
    text = '---\ntitle: "Hello world"\n---\nbody\n'
    meta, _ = split_frontmatter(text)
    assert meta["title"] == "Hello world"


def test_split_strips_trailing_inline_comment_on_unquoted_value():
    text = "---\nstatus: draft              # draft | in-review | approved\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["status"] == "draft"


def test_split_quoted_value_preserves_hash():
    # a GitHub issue ref lives quoted; the '#' must survive (it is not a comment)
    text = '---\nsource_brief: "#42"\n---\nbody\n'
    meta, _ = split_frontmatter(text)
    assert meta["source_brief"] == "#42"


def test_split_preserves_wikilink_value():
    text = '---\nsource_rfc: "[[my feature rfc]]"\n---\nbody\n'
    meta, _ = split_frontmatter(text)
    assert meta["source_rfc"] == "[[my feature rfc]]"


def test_split_inline_list_value():
    text = "---\ndecision_makers: [jose, claude]\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["decision_makers"] == ["jose", "claude"]


def test_split_empty_value_is_empty_string():
    text = "---\nnotes:\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["notes"] == ""


def test_split_value_stays_string_for_numbers():
    text = "---\nstage: 4\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["stage"] == "4"


def test_split_multiple_keys():
    text = '---\ntype: task\ntarget_repo: platform\nsize: "S — one PR"\n---\nbody\n'
    meta, _ = split_frontmatter(text)
    assert meta == {"type": "task", "target_repo": "platform", "size": "S — one PR"}


def test_split_unclosed_frontmatter_treated_as_no_frontmatter():
    # a stray leading '---' with no closing fence is not frontmatter
    text = "---\nnot really frontmatter\nstill body\n"
    meta, body = split_frontmatter(text)
    assert meta == {}
    assert body == text


# --- block-style lists (Obsidian's property editor writes non-empty lists this way) ---

def test_split_block_style_list_single_item():
    text = '---\nsupersedes:\n  - "[[old spec]]"\n---\nbody\n'
    meta, _ = split_frontmatter(text)
    assert meta["supersedes"] == ["[[old spec]]"]


def test_split_block_style_list_multiple_items():
    text = "---\ntags:\n  - alpha\n  - beta\n  - gamma\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["tags"] == ["alpha", "beta", "gamma"]


def test_split_block_style_list_strips_quotes_per_item():
    text = '---\nsupersedes:\n  - "[[a spec]]"\n  - "[[b spec]]"\n---\nbody\n'
    meta, _ = split_frontmatter(text)
    assert meta["supersedes"] == ["[[a spec]]", "[[b spec]]"]


def test_split_block_style_list_followed_by_another_key():
    text = "---\ntags:\n  - alpha\n  - beta\ntype: task\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["tags"] == ["alpha", "beta"]
    assert meta["type"] == "task"


def test_split_block_style_list_tolerates_tab_indented_items():
    text = "---\ntags:\n\t- alpha\n\t- beta\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["tags"] == ["alpha", "beta"]


def test_split_bare_key_with_no_following_dash_items_is_empty_string():
    # a genuinely empty scalar (no block list follows) parses exactly as before
    text = "---\nnotes:\ntype: task\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["notes"] == ""
    assert meta["type"] == "task"


# --- inline lists: per-item quotes stripped (new), existing shape unchanged otherwise ---

def test_split_inline_list_strips_quotes_per_item():
    text = '---\ndecision_makers: ["jose", "claude"]\n---\nbody\n'
    meta, _ = split_frontmatter(text)
    assert meta["decision_makers"] == ["jose", "claude"]


def test_split_inline_list_mixed_quoted_and_unquoted_items():
    text = '---\ntags: [alpha, "beta gamma"]\n---\nbody\n'
    meta, _ = split_frontmatter(text)
    assert meta["tags"] == ["alpha", "beta gamma"]


def test_split_inline_list_unquoted_items_unchanged_regression():
    # existing behavior (no quotes to strip) must still work exactly as before
    text = "---\ndecision_makers: [jose, claude]\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["decision_makers"] == ["jose", "claude"]


def test_split_inline_list_empty_unchanged_regression():
    text = "---\ntags: []\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["tags"] == []


def test_split_scalar_double_quoted_value_unchanged_regression():
    text = '---\ntitle: "Hello world"\n---\nbody\n'
    meta, _ = split_frontmatter(text)
    assert meta["title"] == "Hello world"


def test_split_scalar_unquoted_trailing_comment_unchanged_regression():
    text = "---\nstatus: draft              # draft | in-review | approved\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["status"] == "draft"
