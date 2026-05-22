"""
DST Bridge extension configuration.

Cluster path, command-queue filename.
Formerly part of the monolithic root config.py (Phase 2 split).
"""

# Active cluster directory (change when switching saves)
# e.g. r"D:\Documents\Klei\DoNotStarveTogether\<SteamID>\Cluster_4"
DST_CLUSTER_PATH = r"D:\Documents\Klei\DoNotStarveTogether\325334978\Cluster_4"

# Queue file sits in the active shard's Master/save/ folder
# Resolved at runtime by DSTBridgeExtension._resolve_cmd_queue_file()
DST_CMD_QUEUE_FILENAME = "exo_cmd_queue.txt"
