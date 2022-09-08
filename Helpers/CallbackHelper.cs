using nng_one.Configs;
using nng_one.Containers;
using nng_one.Logging;
using nng.Enums;
using nng.VkFrameworks;
using VkNet.Model;

namespace nng_one.Helpers;

public static class CallbackHelper
{
    private static readonly VkFramework VkFramework = VkFrameworkContainer.GetInstance().VkFramework;
    private static readonly Config Config = ConfigProcessor.LoadConfig();

    private static void SetCallback(this Group group, CallbackOperation operation, bool targetStatus)
    {
        if (!Config.SwitchCallback) return;
        var servers = VkFramework.GetGroupCallbackServes(group).ToList();
        if (!servers.Any()) Logger.Log($"Не найдено Callback серверов у группы {group.Id}", LogType.Debug);
        foreach (var server in servers)
        {
            VkFramework.ChangeGroupCallbackSettings(group, server, operation, targetStatus);
            Logger.Log($"Поменяли Callback сервер {server.Id} c операцией {operation} на {targetStatus}",
                LogType.Debug);
        }
    }

    public static void SetCallback(long group, CallbackOperation operation, bool targetStatus)
    {
        if (!Config.SwitchCallback) return;
        var targetGroup = new Group {Id = group};
        SetCallback(targetGroup, operation, targetStatus);
    }
}
