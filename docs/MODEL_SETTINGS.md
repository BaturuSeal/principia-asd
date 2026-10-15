# Model profiles

Open **API settings → Your model library** in the local companion. Add an exact SiliconFlow model identifier, a readable label, dated input/output prices in CNY per million tokens, and supported reasoning options. Edit or remove any listed model; changes apply only to future runs and invalidate the edited model's capability check. Completed runs retain their immutable request, profile and receipt bindings.

**Browse provider catalog** makes an authenticated GET to SiliconFlow's models endpoint. It makes no generation request. Catalog entries are suggestions, not verified scientific model configurations. The explicit **Check selected models** button sends one small billed text/JSON request per selected model, at most four at once. It does not establish vision support or enable arbitrary native tool calls. Existing methods use structured JSON actions interpreted by the host.

For strict budgeting, disabling thinking is the default. Some models do not accept the thinking option; select the non-reasoning configuration and verify it explicitly. Enabled reasoning requires a token reservation. SiliconFlow's visible output limit does not necessarily bound hidden reasoning, and enforcement varies by model. A detected bound violation stops the run and remains in accounting; the UI does not promise that a user-entered number changes the provider's billing policy.

The gateway never substitutes models, follows arbitrary provider endpoints, or automatically replays ambiguous calls. Update price records when tariffs change. The local ledger is conservative relative to the recorded prices, not an independent guarantee of the provider's current bill.

References: [model catalog API](https://api-docs.siliconflow.cn/docs/api/models-get), [reasoning options](https://docs.siliconflow.cn/docs/userguide/capabilities/reasoning), [pricing](https://www.siliconflow.cn/pricing).
