using nng_one.Configs;
using nng_one.FunctionParameters;
using nng_one.ServiceCollections;
using nng.Constants;
using nng.Enums;
using nng.Helpers;
using nng.Logging;
using nng.VkFrameworks;
using VkNet.Exception;

namespace nng_one.Functions;

public static class Block
{
    private static readonly VkFramework VkFramework = ServiceCollectionContainer.GetInstance().VkFramework;

    private static readonly List<long> UsersFailedToBan = new();
    private static Logger Logger => ServiceCollectionContainer.GetInstance().GlobalLogger;
    private static CallbackHelper CallbackHelper => ServiceCollectionContainer.GetInstance().CallbackHelper;

    public static void Process(BlockParameters blockParameters)
    {
        foreach (var group in blockParameters.Groups)
        {
            Logger.Log($"Переходим к сообществу {group}");
            CallbackHelper.SetCallback(group, CallbackOperation.Editor, false);
            CallbackHelper.SetCallback(group, CallbackOperation.Block, false);

            var users = GetUsersForBan(blockParameters.Users, group).ToList();
            if (!users.Any())
            {
                Logger.Log($"Все пользователи уже заблокированы в сообществе {group}");
                continue;
            }

            foreach (var (user, shouldWeFireEditor) in users)
            {
                if (UsersFailedToBan.Contains(user))
                {
                    Logger.Log($"Пользователя {user} не получилось заблокировать группой раннее", LogType.Debug);
                    continue;
                }

                if (shouldWeFireEditor) FireEditor(user, group);
                BanUser(user, group, blockParameters.Config);
            }

            CallbackHelper.SetCallback(group, CallbackOperation.Editor, true);
            CallbackHelper.SetCallback(group, CallbackOperation.Block, true);
        }

        UsersFailedToBan.Clear();
    }

    private static void BanUser(long user, long group, Config config)
    {
        VkFramework.CaptchaSecondsToWait = Constants.CaptchaBlockWaitTime;
        try
        {
            VkFramework.Block(group, user, config.BanReason);
            Logger.Log($"Заблокировали {user} в сообществе {group}");
        }
        catch (VkApiException e)
        {
            Logger.Log(e);
            Logger.Log($"Не удалось заблокировать {user} в сообществе {group}", LogType.Error);
            UsersFailedToBan.Add(user);
        }
    }

    private static void FireEditor(long user, long group)
    {
        VkFramework.CaptchaSecondsToWait = Constants.CaptchaEditorWaitTime;
        try
        {
            VkFramework.EditManager(user, group, null);
            Logger.Log($"Сняли {user} в сообществе {group}");
        }
        catch (VkApiException e)
        {
            Logger.Log(e);
            Logger.Log($"Не удалось удалить из руководителей {user} в сообществе {group}", LogType.Error);
        }
    }

    private static Dictionary<long, bool> GetUsersForBan(IEnumerable<long> users, long group)
    {
        var workUsers = users.ToList();
        try
        {
            var bannedUsers = VkFramework.GetBanned(group);
            var data = VkFramework.GetGroupData(group);
            var dict = workUsers.Where(bannedUser => bannedUsers.All(x => x.Id != bannedUser))
                .ToDictionary(bannedUser => bannedUser, _ => false);
            foreach (var manager in data.Managers.Where(manager => workUsers.Contains(manager.Id)))
                if (dict.ContainsKey(manager.Id)) dict[manager.Id] = true;
                else dict.Add(manager.Id, true);
            return dict;
        }
        catch (VkApiException e)
        {
            Logger.Log(e);
            return workUsers.ToDictionary(x => x, _ => false);
        }
    }
}
