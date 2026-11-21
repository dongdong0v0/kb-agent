from app.llm import ChatClient


class StubSettings:
    deepseek_base_url = "https://example.test"
    deepseek_model = "stub-model"
    max_tokens = 128
    price_input_per_mtok = 2.0
    price_output_per_mtok = 8.0
    temperature = 0.0

    class deepseek_api_key:
        @staticmethod
        def get_secret_value() -> str:
            return "sk-stub"


class FakeResp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "json": kwargs.get("json")})
        return FakeResp(self.payloads.pop(0))


def _reply(text: str, finish: str = "stop") -> dict:
    return {
        "model": "stub-model",
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_multi_turn_keeps_history() -> None:
    session = FakeSession([_reply("第一答"), _reply("第二答")])
    client = ChatClient(settings=StubSettings(), system_prompt="你是助手", session=session)

    client.send("第一问")
    client.send("第二问")

    second_payload = session.calls[1]["json"]
    roles = [m["role"] for m in second_payload["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_usage_accumulates() -> None:
    session = FakeSession([_reply("a"), _reply("b")])
    client = ChatClient(settings=StubSettings(), session=session)
    client.send("q1")
    client.send("q2")
    assert client.total_tokens_used == 30


def test_truncated_flag() -> None:
    session = FakeSession([_reply("半句话", finish="length")])
    client = ChatClient(settings=StubSettings(), session=session)
    assert client.send("q").truncated is True


def test_reset_keeps_system() -> None:
    client = ChatClient(settings=StubSettings(), system_prompt="你是助手", session=FakeSession([]))
    client.messages.append(__import__("app.llm", fromlist=["Message"]).Message("user", "hi"))
    client.reset()
    assert [m.role for m in client.messages] == ["system"]
