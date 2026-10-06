from app.runtime.decision_parser import LLMDecisionParser


def test_parser_handles_normal_response():
    parser = LLMDecisionParser()

    decision = parser.parse(
        {
            "message": {
                "content": "I found the contract.",
            }
        }
    )

    assert decision.content == "I found the contract."
    assert decision.tool_calls == []
    assert decision.requires_tool_execution is False


def test_parser_handles_tool_call():
    parser = LLMDecisionParser()

    decision = parser.parse(
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_contract",
                            "arguments": {
                                "query": "Villa ABC",
                            },
                        }
                    }
                ],
            }
        }
    )

    assert decision.requires_tool_execution is True

    assert len(decision.tool_calls) == 1

    tool_call = decision.tool_calls[0]

    assert tool_call.name == "search_contract"
    assert tool_call.arguments == {
        "query": "Villa ABC",
    }


def test_parser_handles_multiple_tool_calls():
    parser = LLMDecisionParser()

    decision = parser.parse(
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_contract",
                            "arguments": {
                                "query": "Villa ABC",
                            },
                        }
                    },
                    {
                        "function": {
                            "name": "search_contract",
                            "arguments": {
                                "query": "Villa XYZ",
                            },
                        }
                    },
                ],
            }
        }
    )

    assert len(decision.tool_calls) == 2

    assert (
        decision.tool_calls[0].arguments["query"]
        == "Villa ABC"
    )

    assert (
        decision.tool_calls[1].arguments["query"]
        == "Villa XYZ"
    )


def test_parser_handles_empty_response():
    parser = LLMDecisionParser()

    decision = parser.parse(None)

    assert decision.content is None
    assert decision.tool_calls == []
    assert decision.requires_tool_execution is False