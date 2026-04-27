# tests/test_vnext_llm_engine.py
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_llm_engine_importable():
    print("\nTest: llm_engine importable")
    try:
        from agent_analysis.llm_engine import LLMEngine
        assert LLMEngine is not None
        print("[PASS] LLMEngine imported")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def test_token_tracking():
    print("\nTest: token tracking")
    try:
        from agent_analysis.llm_engine import LLMEngine
        engine = LLMEngine(available_models=[])
        engine.token_usage["stage_A"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        engine.token_usage["stage_B"] = {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
        report = engine.get_token_report()
        assert report["stage_A"]["total_tokens"] == 15
        assert report["stage_B"]["total_tokens"] == 30
        print("[PASS] Token tracking works")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def main():
    results = [
        ("importable", test_llm_engine_importable()),
        ("token_tracking", test_token_tracking()),
    ]
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\nResults: {passed}/{total} passed")
    return passed == total


if __name__ == "__main__":
    exit(0 if main() else 1)
