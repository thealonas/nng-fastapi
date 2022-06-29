using nng.Enums;
using nng.VkFrameworks;
using nng_one.Containers;
using nng_one.FunctionParameters;
using nng_one.Helpers;
using nng_one.Logging;
using VkNet.Exception;

namespace nng_one.Functions;

public static class Unblock
{
    private static readonly VkFramework VkFramework = VkFrameworkContainer.GetInstance().VkFramework;

    public static void Process(UnblockParameters unblockParameters)
    {
        if (unblockParameters.Users == null)
        {
            foreach (var group in unblockParameters.Groups)
            {
                Logger.Log($"Переходим к сообществу {group.Id}");
                CallbackHelper.SetCallback(group.Id, CallbackOperation.Block, false);
                UnblockInCommunity(group.Id);
                CallbackHelper.SetCallback(group.Id, CallbackOperation.Block, true);
            }

            return;
        }

        foreach (var group in unblockParameters.Groups)
        {
            Logger.Log($"Переходим к сообществу {group.Id}");
            CallbackHelper.SetCallback(group.Id, CallbackOperation.Block, false);
            UnblockUsers(group.Id, unblockParameters.Users.Select(x => x.Id));
            CallbackHelper.SetCallback(group.Id, CallbackOperation.Block, true);
        }
    }

    private static void UnblockInCommunity(long group)
    {
        var data = VkFramework.GetBanned(group).ToList();
        if (!data.Any())
        {
            Logger.Log($"В сообществе {group} заблокированных пользователей нет", LogType.Warning);
            return;
        }

        foreach (var user in data) UnblockUser(group, user.Id);
    }

    private static void UnblockUsers(long group, IEnumerable<long> users)
    {
        var data = VkFramework.GetBanned(group);
        var operationalUsers = users.Where(x => data.Any(y => y.Id == x)).ToList();
        if (!operationalUsers.Any())
        {
            Logger.Log($"В сообществе {group} заблокированных пользователей нет", LogType.Warning);
            return;
        }

        foreach (var user in operationalUsers) UnblockUser(group, user);
    }

    private static void UnblockUser(long group, long user)
    {
        VkFramework.CaptchaSecondsToWait = 10;
        try
        {
            VkFramework.UnBlock(group, user);
            Logger.Log($"Разблокировали {user} в сообществе {group}");
        }
        catch (VkApiException e)
        {
            Logger.Log($"Не удалось разблокировать {user} в сообществе {group}", LogType.Error);
            Logger.Log(e);
        }
    }
}
