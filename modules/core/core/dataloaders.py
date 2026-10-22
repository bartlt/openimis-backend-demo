from graphql_sync_dataloaders import SyncDataLoader


class DataLoader(SyncDataLoader):
    """
    Batching DataLoader for synchronous graphql-core 3 execution.

    Replaces ``promise.dataloader.DataLoader``: subclasses implement
    ``batch_load_fn(keys)`` and return the values (a plain list, in key order).
    Batching relies on ``DeferredExecutionContext``, set on the GraphQL view.
    """

    def __init__(self):
        super().__init__(self.batch_load_fn)

    def batch_load_fn(self, keys):
        raise NotImplementedError
