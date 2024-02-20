from nng_sdk.vk.actions import vk_action
from nng_sdk.vk.vk_manager import VkManager


@vk_action
def unban_in_group(user: int, group: int):
    VkManager().get_executable_api().groups.unban(group_id=group, owner_id=user)


@vk_action
def ban_in_group(user: int, group: int):
    VkManager().get_executable_api().groups.ban(group_id=group, owner_id=user)
