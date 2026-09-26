# Bolt's Journal - Critical Learnings

## 2025-05-18 - SqliteSaver Checkpoint Iteration Overhead
**Learning:** LangGraph's `checkpointer.list(None)` yields every historical checkpoint across all threads, including intermediate state steps. Iterating through `list(None)` unindexed or without thread deduplication in SQL results in O(N_checkpoints) scans rather than O(N_threads), causing quadratic performance degradation as chat threads grow.
**Action:** Use direct SQL queries on `checkpoint_blobs` / `checkpoints` tables or distinct thread filtering when retrieving thread list to query O(N_threads) rather than scanning all checkpoints.
