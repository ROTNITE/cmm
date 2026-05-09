import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch


class ConfigTests(unittest.TestCase):
    def test_profile_defaults_resolve_to_gpt41_stage_settings(self):
        import Lib.config as config

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(json.dumps({"profile": "gpt-4.1"}, ensure_ascii=False), encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "CMM_CONFIG_PATH": str(config_path),
                    "CMM_MODEL_PROFILE": "gpt-4.1",
                },
                clear=True,
            ):
                self.assertEqual(config.get_model_profile_name(), "gpt-4.1")
                profile = config.get_model_profile()
                self.assertEqual(profile["model"], "gpt-4.1")
                self.assertEqual(config.get_default_model(), "gpt-4.1")
                self.assertEqual(config.get_stage_settings("planner")["tokens"], 1000)
                self.assertEqual(config.get_stage_settings("judge")["temp"], 0.1)

    def test_env_model_override_is_used_by_send_to_ai_default(self):
        """Test that config file model takes priority over env vars.

        NEW BEHAVIOR: cmm_config.json has HIGHEST priority.
        Env vars are ignored if config file has model set.
        """
        import Lib.AI_request as ai_request
        import Lib.config as config

        captured = {}

        class _Message:
            content = "ok"

        class _Choice:
            message = _Message()

        class _Response:
            choices = [_Choice()]

        class _Completions:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return _Response()

        class _Chat:
            completions = _Completions()

        class _Client:
            chat = _Chat()

            def __init__(self, **kwargs):
                captured["client"] = kwargs

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps({
                    "model": "config-file-model",
                    "api": {"base_url": "http://config-file.local/v1"}
                }, ensure_ascii=False),
                encoding="utf-8"
            )

            with patch.dict(
                os.environ,
                {
                    "CMM_CONFIG_PATH": str(config_path),
                    "CMM_MODEL": "env-var-model",  # This should be IGNORED
                    "CMM_BASE_URL": "http://env-var.local/v1",  # This should be IGNORED
                },
                clear=True,
            ), patch.object(ai_request, "_load_local_env_files", return_value=None), patch.dict(
                "sys.modules", {"openai": type("OpenAIModule", (), {"OpenAI": _Client})}
            ):
                result = ai_request.send_to_AI("hello", tokens=10, api_key="test-secret")

            self.assertEqual(result, "ok")
            # Config file model takes priority over env var
            self.assertEqual(captured["model"], "config-file-model")
            self.assertEqual(captured["client"]["base_url"], "http://config-file.local/v1")

    def test_orchestrator_defaults_come_from_config_env(self):
        """Test that runtime defaults (max_iters, route_mode) can be overridden by env.

        NEW BEHAVIOR: model comes from config file (highest priority),
        but runtime settings like max_iters, route_mode can be overridden by env.
        """
        from Lib.orchestrator import run_cmm

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps({
                    "model": "config-file-model",
                    "defaults": {
                        "max_iters": 2,
                        "route_mode": "AUTO",
                    }
                }, ensure_ascii=False),
                encoding="utf-8"
            )

            with patch.dict(
                os.environ,
                {
                    "CMM_CONFIG_PATH": str(config_path),
                    "CMM_MODEL": "env-model",  # IGNORED - config file wins
                    "CMM_ROUTE_MODE": "FULL_CMM",  # Used - runtime setting
                    "CMM_PARALLEL_MODE": "THREADS",  # Used - runtime setting
                    "CMM_MAX_WORKERS": "3",  # Used - runtime setting
                    "CMM_MAX_DELIBERATION_ROUNDS": "2",  # Used - runtime setting
                    "CMM_MAX_ITERS": "4",  # Used - runtime setting
                },
                clear=True,
            ), patch(
                "Lib.orchestrator.run_cmm_state_machine",
                return_value={"final_answer": "", "trace_report": {}, "raw": {}},
            ) as mock:
                run_cmm("query")

            # Model comes from config file, runtime settings from env
            mock.assert_called_once_with(
                "query",
                max_iters=4,
                model="config-file-model",  # From config file, not env
                route_mode="FULL_CMM",
                parallel_mode="THREADS",
                max_workers=3,
                max_deliberation_rounds=2,
            )

    def test_judge_model_can_differ_via_profile_override(self):
        """Test that judge_model can be set in config file independently.

        NEW BEHAVIOR: judge_model comes from config file, not env vars.
        """
        import Lib.config as config

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps({
                    "profile": "gpt-4.1",
                    "model": "gpt-4.1",
                    "judge_model": "gpt-4.1-mini"
                }, ensure_ascii=False),
                encoding="utf-8"
            )
            with patch.dict(
                os.environ,
                {
                    "CMM_CONFIG_PATH": str(config_path),
                    "CMM_MODEL_PROFILE": "gpt-4.1",
                    "CMM_JUDGE_MODEL": "env-judge-model",  # IGNORED - config file wins
                },
                clear=True,
            ):
                self.assertEqual(config.get_default_model(), "gpt-4.1")
                # Judge model comes from config file, not env
                self.assertEqual(config.get_judge_model(), "gpt-4.1-mini")

    def test_judge_model_can_follow_explicit_runtime_model(self):
        import Lib.config as config

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps({
                    "model": "config-main-model",
                    "judge_model": "config-judge-model"
                }, ensure_ascii=False),
                encoding="utf-8"
            )
            with patch.dict(
                os.environ,
                {
                    "CMM_CONFIG_PATH": str(config_path),
                },
                clear=True,
            ):
                self.assertEqual(
                    config.get_judge_model(None, fallback_model="kr/claude-sonnet-4.5"),
                    "kr/claude-sonnet-4.5",
                )

    def test_config_import_is_silent(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            import Lib.config as config

            self.assertTrue(config.load_config())

        self.assertEqual(buffer.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
