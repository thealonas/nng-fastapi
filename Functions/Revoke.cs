using nng_one.Configs;
using nng_one.ServiceCollections;
using nng.Constants;
using nng.Enums;
using nng.Helpers;
using nng.Logging;
using nng.VkFrameworks;
using VkNet.Enums.Filters;
using VkNet.Enums.SafetyEnums;
using VkNet.Exception;
using VkNet.Model;
using VkNet.Model.RequestParams;
using VkNet.Utils;

namespace nng_one.Functions;

public static class Revoke
{
    private static readonly VkFramework VkFramework = ServiceCollectionContainer.GetInstance().VkFramework;
    private static readonly Logger Logger = ServiceCollectionContainer.GetInstance().GlobalLogger;
    private static readonly CallbackHelper CallbackHelper = ServiceCollectionContainer.GetInstance().CallbackHelper;

    private static readonly bool CallbackIsAllowed = ConfigProcessor.LoadConfig().SwitchCallback;

    public static void DoRevoke(IEnumerable<Group> groups)
    {
        foreach (var group in groups)
        {
            Logger.Log($"Обрабатываем группу {group.Id}");
            var users = GetInactiveEditorsInGroup(group).ToList();

            if (!users.Any())
            {
                Logger.Log("Неактивных редакторов не найдено");
                continue;
            }

            CallbackHelper.SetCallback(group.Id, CallbackOperation.Editor, false, CallbackIsAllowed);
            foreach (var user in users) FireEditor(group.Id, user);
            CallbackHelper.SetCallback(group.Id, CallbackOperation.Editor, true, CallbackIsAllowed);
        }
    }

    private static IEnumerable<long> GetInactiveEditorsInGroup(IVkModel group)
    {
        var users = VkFrameworkExecution.ExecuteWithReturn(() =>
            VkFramework.Api.Groups.GetMembers(new GroupsGetMembersParams
            {
                Count = 1000, Fields = UsersFields.LastSeen, Filter = GroupsMemberFilters.Managers,
                GroupId = group.Id.ToString(), Offset = 0, Sort = GroupsSort.TimeAsc
            }));

        return users is null
            ? ArraySegment<long>.Empty
            : users.Where(x => x.LastSeen.Time is not null && IsLate((DateTime)x.LastSeen.Time)).Select(x => x.Id);
    }

    private static void FireEditor(long group, long editor)
    {
        VkFramework.CaptchaSecondsToWait = Constants.CaptchaEditorWaitTime;
        try
        {
            VkFramework.EditManager(editor, group, null);
            Logger.Log($"Сняли редактора {editor} в сообществе {group}");
        }
        catch (VkApiException e)
        {
            Logger.Log($"Не удалось снять редактора {editor} в сообществе {group}", LogType.Error);
            Logger.Log(e);
        }
    }

    private static bool IsLate(DateTime time)
    {
        return time.AddMonths(6) < DateTime.Now;
    }
}
