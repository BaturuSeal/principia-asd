# Execution boundary

The release's default rule language is a restricted expression DSL. It accepts arithmetic and an audited function allowlist, rejects attributes/imports/statements, and never executes arbitrary generated Python. A future arbitrary-program adapter must provide a verified macOS sandbox with network, credentials, private evaluator files, and sibling scenarios denied before it can be used for scored runs.
