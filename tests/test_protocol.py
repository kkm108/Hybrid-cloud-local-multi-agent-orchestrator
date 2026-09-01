"""T02: Protocol parser tests (§5 grammar)."""

from socialai.protocol import (
    VERBS,
    parse_blocks,
    parse_message,
    serialize_block,
)


class TestSingleBlock:
    def test_freetext_body(self) -> None:
        msg = "[SEND_TO: deepseek_1] Write me a poem [/SEND_TO]"
        blocks = parse_blocks(msg)
        assert len(blocks) == 1
        assert blocks[0].target == "deepseek_1"
        assert blocks[0].body == "Write me a poem"

    def test_trims_whitespace(self) -> None:
        msg = "  [SEND_TO: gemini1_1]   hello   [/SEND_TO]  "
        blocks = parse_blocks(msg)
        assert len(blocks) == 1
        assert blocks[0].target == "gemini1_1"
        assert blocks[0].body == "hello"

    def test_manual_input_target(self) -> None:
        msg = "[SEND_TO: manual_input] Approve? [/SEND_TO]"
        blocks = parse_blocks(msg)
        assert blocks[0].target == "manual_input"


class TestConfigVerbs:
    def test_config_kv_extracted(self) -> None:
        for key in ("TEMPERATURE", "TOP_P", "TOP_K", "MAX_TOKENS", "REPETITION_PENALTY"):
            msg = f"[SEND_TO: local_1] {key}: 0.8 [/SEND_TO]"
            b = parse_blocks(msg)[0]
            assert b.verb == key
            assert b.value == "0.8"

    def test_system_prompt_kv(self) -> None:
        msg = "[SEND_TO: local_1] SYSTEM_PROMPT: You are helpful [/SEND_TO]"
        b = parse_blocks(msg)[0]
        assert b.verb == "SYSTEM_PROMPT"
        assert b.value == "You are helpful"


class TestActionVerbs:
    def test_action_verb_extracted(self) -> None:
        for verb in VERBS:
            msg = f"[SEND_TO: w_1] ACTION: {verb} [/SEND_TO]"
            b = parse_blocks(msg)[0]
            assert b.verb == "ACTION"
            assert b.value == verb
            assert b.is_action

    def test_unknown_action_still_captured(self) -> None:
        msg = "[SEND_TO: w_1] ACTION: FLIP_TABLE [/SEND_TO]"
        b = parse_blocks(msg)[0]
        assert b.verb == "ACTION"
        assert b.value == "FLIP_TABLE"


class TestMultiBlock:
    def test_multiple_blocks_parsed(self) -> None:
        msg = (
            "[SEND_TO: a_1] first [/SEND_TO] "
            "[SEND_TO: b_1] second [/SEND_TO] "
            "[SEND_TO: c_1] third [/SEND_TO]"
        )
        blocks = parse_blocks(msg)
        assert [b.target for b in blocks] == ["a_1", "b_1", "c_1"]
        assert [b.body for b in blocks] == ["first", "second", "third"]

    def test_multiple_blocks_same_target(self) -> None:
        msg = "[SEND_TO: x_1] one [/SEND_TO] [SEND_TO: x_1] two [/SEND_TO]"
        assert len(parse_blocks(msg)) == 2


class TestNestedBrackets:
    def test_free_text_with_brackets(self) -> None:
        msg = "[SEND_TO: g_1] use [this] and {that} [/SEND_TO]"
        blocks = parse_blocks(msg)
        assert len(blocks) == 1
        assert blocks[0].body == "use [this] and {that}"

    def test_nested_send_to_inside_body(self) -> None:
        msg = (
            "[SEND_TO: g_1] outer start "
            "[SEND_TO: inner_1] deeper [/SEND_TO] outer end [/SEND_TO]"
        )
        blocks = parse_blocks(msg)
        assert len(blocks) == 1
        assert blocks[0].target == "g_1"
        assert "outer start" in blocks[0].body
        assert "outer end" in blocks[0].body
        assert blocks[0].body.startswith("outer start")


class TestFreeText:
    def test_unblocked_text_is_free(self) -> None:
        msg = "just some free text with no blocks"
        result = parse_message(msg)
        assert result.blocks == []
        assert result.free_text == msg

    def test_mixes_blocks_and_free_text(self) -> None:
        msg = "intro text [SEND_TO: a_1] body [/SEND_TO] outro text"
        result = parse_message(msg)
        assert len(result.blocks) == 1
        assert result.blocks[0].target == "a_1"
        assert result.free_text == "intro text outro text"


class TestMalformedTolerance:
    def test_unclosed_block_ignored(self) -> None:
        msg = "[SEND_TO: a_1] never closed"
        assert parse_blocks(msg) == []

    def test_closer_without_opener_ignored(self) -> None:
        msg = "[/SEND_TO] stray closer"
        assert parse_blocks(msg) == []


class TestSerialize:
    def test_roundtrip(self) -> None:
        body = "Write poem"
        text = serialize_block("deepseek_1", body)
        blocks = parse_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].target == "deepseek_1"
        assert blocks[0].body == body
