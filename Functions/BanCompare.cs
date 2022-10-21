using nng_one.FunctionParameters;
using nng_one.Input;
using nng_one.ServiceCollections;
using nng.Constants;
using nng.Enums;
using nng.Helpers;
using nng.Logging;
using nng.VkFrameworks;
using VkNet.Exception;
using VkNet.Model;

namespace nng_one.Functions;

public static class BanCompare
{
    private static readonly VkFramework VkFramework = ServiceCollectionContainer.GetInstance().VkFramework;
    private static readonly Logger Logger = ServiceCollectionContainer.GetInstance().GlobalLogger;
    private static readonly CallbackHelper CallbackHelper = ServiceCollectionContainer.GetInstance().CallbackHelper;
    private static readonly InputHandler InputHandler = InputHandler.GetInstance();

    private static readonly Dictionary<long, Dictionary<long, bool>> UsersThatShouldBeBanned = new();
    private static readonly Dictionary<long, List<long>> UsersThatShouldBeUnbanned = new();
    private static readonly List<long> UsersFailedToBan = new();

    public static void Process(BanCompareParameters parameters)
    {
        foreach (var group in parameters.Groups)
        {
            var banned = VkFramework.GetBanned(group).ToList();
            var managers = VkFramework.GetGroupData(group).Managers.ToList();
            var shouldBeBanned =
                GetUsersThatShouldBeBanned(parameters.Users, banned, managers.Select(x => x.Id).ToList()).ToList();
            var shouldNotBeBanned = GetUsersThatShouldNotBeBanned(parameters.Users, banned).ToList();

            if (shouldBeBanned.Count > 0)
                UsersThatShouldBeBanned.Add(group, shouldBeBanned.ToDictionary(x => x.Key, x => x.Value));

            if (shouldNotBeBanned.Count > 0) UsersThatShouldBeUnbanned.Add(group, shouldNotBeBanned);

            if (shouldBeBanned.Any() || shouldNotBeBanned.Any())
                Logger.Log($"В сообществе {group} найдены отклонения");
        }

        if (!UsersThatShouldBeBanned.Any() && !UsersThatShouldBeUnbanned.Any())
        {
            Logger.Log("Отклонений в сообществах нет");
            return;
        }

        if (!InputHandler.GetBoolInput("Приступить к исправлению отклонений?")) return;

        Logger.Clear();

        if (UsersThatShouldBeBanned.Any())
        {
            Logger.Log("Начинаем блокировку");
            foreach (var (group, users) in UsersThatShouldBeBanned)
            {
                Logger.Log($"Переходим к сообществу {group}");
                ProcessUsersBan(group, users, parameters.Config.BanReason);
            }
        }
        else
        {
            Logger.Log("Отклонений на блокировку нет");
        }

        if (UsersThatShouldBeUnbanned.Any())
        {
            Logger.Log("Начинаем разблокировку");
            foreach (var (group, users) in UsersThatShouldBeUnbanned)
            {
                Logger.Log($"Переходим к сообществу {group}");
                ProcessUsersUnban(group, users);
            }
        }
        else
        {
            Logger.Log("Отклонений на разблокировку нет");
        }
    }

    private static void ProcessUsersBan(long group, Dictionary<long, bool> users, string banComment)
    {
        CallbackHelper.SetCallback(group, CallbackOperation.Block, false);
        CallbackHelper.SetCallback(group, CallbackOperation.Editor, false);
        foreach (var (user, shouldFire) in users)
        {
            if (UsersFailedToBan.Contains(user))
            {
                Logger.Log($"Пользователя {user} не получилось заблокировать группой раннее", LogType.Debug);
                continue;
            }

            if (shouldFire) FireEditor(user, group);

            BanUser(user, group, banComment);
        }

        CallbackHelper.SetCallback(group, CallbackOperation.Block, true);
        CallbackHelper.SetCallback(group, CallbackOperation.Editor, true);
    }

    private static void ProcessUsersUnban(long group, IEnumerable<long> users)
    {
        foreach (var user in users) UnblockUser(user, group);
    }

    private static void BanUser(long user, long group, string banReason)
    {
        VkFramework.CaptchaSecondsToWait = Constants.CaptchaBlockWaitTime;
        try
        {
            VkFramework.Block(group, user, banReason);
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

    private static void UnblockUser(long user, long group)
    {
        VkFramework.CaptchaSecondsToWait = Constants.CaptchaBlockWaitTime;
        try
        {
            VkFramework.UnBlock(group, user);
            Logger.Log($"Разблокировали {user} в сообществе {group}");
        }
        catch (VkApiException e)
        {
            Logger.Log(e);
            Logger.Log($"Не удалось разблокировать {user} в сообществе {group}", LogType.Error);
        }
    }

    private static Dictionary<long, bool> GetUsersThatShouldBeBanned(IEnumerable<long> bannedUsers,
        IEnumerable<User> currentBannedUsers, ICollection<long> managers)
    {
        var targetsToBan = bannedUsers.Where(x => currentBannedUsers.All(y => y.Id != x)).ToList();
        var output = new Dictionary<long, bool>();
        foreach (var target in targetsToBan)
        {
            var isManager = managers.Contains(target);
            output.Add(target, isManager);
        }

        return output;
    }

    private static IEnumerable<long> GetUsersThatShouldNotBeBanned(IEnumerable<long> bannedUsers,
        IEnumerable<User> currentBannedUsers)
    {
        return currentBannedUsers.Where(x => bannedUsers.All(y => y != x.Id)).Select(x => x.Id).ToList();
    }
}
