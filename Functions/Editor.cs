using nng.Enums;
using nng.VkFrameworks;
using nng_one.Containers;
using nng_one.Extensions;
using nng_one.FunctionParameters;
using nng_one.Helpers;
using nng_one.Logging;
using VkNet.Enums.SafetyEnums;
using VkNet.Exception;
using VkNet.Model;

namespace nng_one.Functions;

public static class Editor
{
    private static readonly VkFramework VkFramework = VkFrameworkContainer.GetInstance().VkFramework;

    public static void Process(EditorParameters parameters)
    {
        if (parameters.Users == null)
        {
            foreach (var group in parameters.Groups)
            {
                Logger.Log($"Переходим к группе {group.Id}");
                CallbackHelper.SetCallback(group.Id, CallbackOperation.Editor, false);
                ProcessEditorWithGroupMembers(group.Id, parameters.Type);
                CallbackHelper.SetCallback(group.Id, CallbackOperation.Editor, true);
            }

            return;
        }

        foreach (var group in parameters.Groups)
        {
            Logger.Log($"Переходим к группе {group.Id}");
            CallbackHelper.SetCallback(group.Id, CallbackOperation.Editor, false);
            ProcessEditor(group.Id, parameters.Users, parameters.Type);
            CallbackHelper.SetCallback(group.Id, CallbackOperation.Editor, true);
        }
    }

    private static void ProcessEditor(long group, IEnumerable<User> users, EditorOperationType type)
    {
        var data = VkFramework.GetGroupData(group);

        var workList = type == EditorOperationType.Give
            ? users.Where(x => data.Managers.All(y => y.Id != x.Id)).ToList()
            : users.Where(x => data.Managers.Any(y => y.Id == x.Id) && x.Role == ManagerRole.Editor).ToList();

        if (!workList.Any())
        {
            Logger.Log(type == EditorOperationType.Give
                ? "Запрошенные пользователи уже являются менеджерами группы"
                : "Запрошенные пользователи не являются менеджерами группы", LogType.Error);
            return;
        }

        foreach (var user in workList)
            if (type == EditorOperationType.Give) GiveEditor(group, user.Id);
            else FireEditor(group, user.Id);
    }

    private static void ProcessEditorWithGroupMembers(long group, EditorOperationType type)
    {
        var data = VkFramework.GetGroupData(group);

        var users = type == EditorOperationType.Give
            ? data.AllUsers.Where(x => !x.IsDeactivated && !data.Managers.Select(y => y.Id).Contains(x.Id))
                .ToList()
                .CutTo(100 - data.Managers.Count)
            : data.Managers.Where(x => x.Role.Equals(ManagerRole.Editor)).ToList();

        if (!users.Any())
        {
            Logger.Log(type == EditorOperationType.Give
                ? "В данном сообществе отсутствуют свободные слоты"
                : "Нет доступных пользователей к снятию", LogType.Error);
            return;
        }

        Logger.Log($"Количество пользователей: {users.Count}", LogType.Debug);
        foreach (var user in users)
            if (type == EditorOperationType.Give) GiveEditor(group, user.Id);
            else FireEditor(group, user.Id);
    }

    private static void GiveEditor(long group, long user)
    {
        VkFramework.CaptchaSecondsToWait = 3600;
        try
        {
            VkFramework.EditManager(user, group, ManagerRole.Editor);
            Logger.Log($"Выдали редактора {user} в сообществе {group}");
        }
        catch (VkApiException e)
        {
            Logger.Log($"Не возможно выдать редактора {user} в сообществе {group}", LogType.Error);
            Logger.Log(e);
        }
    }

    private static void FireEditor(long group, long editor)
    {
        VkFramework.CaptchaSecondsToWait = 3600;
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
}
