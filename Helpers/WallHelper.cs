using nng_one.ServiceCollections;
using nng.Enums;
using nng.Logging;
using nng.VkFrameworks;
using VkNet.Enums;
using VkNet.Exception;

namespace nng_one.Helpers;

public static class WallHelper
{
    private static readonly VkFramework VkFramework = ServiceCollectionContainer.GetInstance().VkFramework;
    private static readonly Logger Logger = ServiceCollectionContainer.GetInstance().GlobalLogger;

    public static WallContentAccess SetWall(long group, WallContentAccess state)
    {
        var old = state is WallContentAccess.Opened ? WallContentAccess.Off : WallContentAccess.Opened;
        try
        {
            old = VkFramework.SetWall(group, state);
            Logger.Log($"Установили стену в группе {group} в состояние {state}", LogType.Debug);
        }
        catch (VkApiException e)
        {
            Logger.Log(e);
            Logger.Log($"Не удалось переключить стену на {state} в сообществе {group}", LogType.Error);
        }

        return old;
    }
}
