from nng_sdk.vk.actions import GroupDataResponse, get_groups_data


class GroupDataStorage:
    groups: dict[int, GroupDataResponse] = []

    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super(GroupDataStorage, cls).__new__(cls)
        return cls.instance

    def get_group(self, group_id: int):
        return self.groups[group_id]

    def update_group(self, group_id: int):
        groups_data = get_groups_data([group_id])
        self.groups[group_id] = groups_data[group_id]

    def update_groups(self, groups: dict[int, GroupDataResponse]):
        self.groups = groups.copy()
        for group_id, group_data in groups.items():
            self.groups[group_id] = group_data
