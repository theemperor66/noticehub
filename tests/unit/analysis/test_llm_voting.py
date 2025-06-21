from typing import Any, Dict, Optional

from src.llm.base_llm import BaseLLM
from main import analyze_with_voting

class DummyLLM(BaseLLM):
    def __init__(self, responses):
        super().__init__(None, None)
        self.responses = responses
        self.idx = 0

    def generate_text(self, prompt: str, max_tokens: int = 1500, temperature: float = 0.7, **kwargs) -> str:
        return ""

    def analyze_text(self, text: str, prompt_template: str, **kwargs) -> Dict[str, Any]:
        resp = self.responses[self.idx % len(self.responses)]
        self.idx += 1
        return resp

def _base_resp(service: str) -> Dict[str, Any]:
    return {
        "extracted_service_name": service,
        "event_start_time": None,
        "event_end_time": None,
        "notification_type": "info",
        "event_summary": "demo",
        "severity_level": "low",
    }


def test_analyze_with_voting_majority():
    responses = [_base_resp("AWS"), _base_resp("Azure"), _base_resp("AWS")]
    llm = DummyLLM(responses)
    result = analyze_with_voting(
        llm,
        text="hello",
        prompt_template="{text}",
        votes=3,
        service_options="AWS, Azure",
    )
    assert result["extracted_service_name"] == "AWS"
