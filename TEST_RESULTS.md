# AgriMind AI – automated test results

Run: 2026-11-24 15:14 IST · Python 3.13.18 · openai 3.58.0

```
tests/test_api.py::test_health_and_seed PASSED
tests/test_api.py::test_auth_rules PASSED
tests/test_api.py::test_upload_search_delete PASSED
tests/test_api.py::test_pdf_ingestion PASSED
tests/test_api.py::test_chat_without_llm_falls_back PASSED
tests/test_api.py::test_chat_rag_with_llm PASSED
tests/test_api.py::test_conversation_isolation PASSED
tests/test_api.py::test_lab_compare_and_generation_eval PASSED
tests/test_api.py::test_retrieval_eval PASSED
tests/test_api.py::test_disease_prediction PASSED
tests/test_api.py::test_soil_crop_fertiliser_irrigation PASSED
tests/test_api.py::test_market_csv_import PASSED
tests/test_api.py::test_admin PASSED
tests/test_api.py::test_sentence_transformer_path PASSED
tests/test_xai.py::test_success_request_shape_and_usage PASSED
tests/test_xai.py::test_rate_limit_retry_honours_retry_after PASSED
tests/test_xai.py::test_rate_limit_exhausted PASSED
tests/test_xai.py::test_server_error_then_success PASSED
tests/test_xai.py::test_auth_error_no_retry_and_key_not_leaked PASSED
tests/test_xai.py::test_unknown_model PASSED
tests/test_xai.py::test_timeout PASSED
tests/test_xai.py::test_network_error_and_missing_key PASSED
tests/test_xai.py::test_list_models PASSED
tests/test_xai.py::test_settings_never_expose_key PASSED
tests/test_xai.py::test_gemini_install_migrates PASSED
tests/test_xai.py::test_chat_rag_with_grok PASSED
tests/test_xai.py::test_grok_failure_falls_back_to_retrieval PASSED
tests/test_xai.py::test_citation_metrics PASSED
tests/test_xai.py::test_lab_comparison_all_metrics PASSED
tests/test_xai.py::test_generation_eval_summary PASSED
tests/test_xai_live.py::test_live_models_and_connectivity SKIPPED (X...)
tests/test_xai_live.py::test_live_rag_answer_with_citations SKIPPED
tests/test_xai_live.py::test_live_kannada_answer SKIPPED (XAI_API_KE...)
tests/test_xai_live.py::test_live_three_way_comparison SKIPPED (XAI_...)
tests/test_xai_live.py::test_live_bad_key_is_reported SKIPPED (XAI_A...)
================== 30 passed, 5 skipped, 2 warnings in 10.53s ==================
```

The 5 skipped tests are the genuine xAI tests (tests/test_xai_live.py). They were skipped because no XAI_API_KEY was available and api.x.ai is not reachable from the build environment. Run test-grok-windows.bat with your key to execute them.
