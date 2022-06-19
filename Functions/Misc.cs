using nng.Enums;
using nng.Models;
using nng.VkFrameworks;
using nng_one.Containers;
using nng_one.FunctionParameters;
using nng_one.Helpers;
using nng_one.Interfaces;
using nng_one.Logging;
using VkNet.Enums;
using VkNet.Exception;
using VkNet.Model;
using VkNet.Utils;
using CaptchaHandler = nng_one.Helpers.CaptchaHandler;

namespace nng_one.Functions;

public static class Misc
{
    private static readonly VkFramework VkFramework = VkFrameworkContainer.GetInstance().VkFramework;
    private static readonly DataModel Data = DataContainer.GetInstance().Model;

    public static void Process(IFunctionParameter functionParameter)
    {
        switch (functionParameter)
        {
            case MiscParameters parameters:
                ProcessMisc(parameters);
                break;
            case GroupWallParameters parameters:
                ProcessGroupWall(parameters);
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(functionParameter), functionParameter, null);
        }
    }

    #region Wall

    private static void ProcessGroupWall(GroupWallParameters parameters)
    {
        switch (parameters.Type)
        {
            case GroupWallParametersType.Repost:
                if (parameters.PostId == null) throw new InvalidOperationException();
                VkFramework.SetCaptchaSolver(new CaptchaHandler());
                ProcessRepost(parameters.Groups, parameters.PostId);
                break;
            case GroupWallParametersType.DeleteAllPosts:
                DeleteAllPostsEntryPoint(parameters.Groups);
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(parameters), parameters, null);
        }
    }

    private static void ProcessRepost(IEnumerable<Group> groups, string post)
    {
        foreach (var group in groups) ProcessRepostInGroup(group, post);
    }

    private static void ProcessRepostInGroup(Group group, string post)
    {
        try
        {
            VkFramework.Repost(group, post);
            Logger.Log($"Сделали репост {post} в сообщество {group.Id}");
        }
        catch (VkApiException e)
        {
            Logger.Log($"Не удалось произвести репост {post} в сообщество {group}");
            Logger.Log(e);
        }
    }

    private static void DeleteAllPostsEntryPoint(IEnumerable<Group> groups)
    {
        foreach (var group in groups)
        {
            Logger.Log($"Переходим к сообществу {group.Id}");
            CallbackHelper.SetCallback(group.Id, CallbackOperation.Wall, false);

            var oldWall = WallHelper.SetWall(group.Id, WallContentAccess.Restricted);

            Logger.Log($"Оригинальное значение стены: {oldWall.ToString()}", LogType.Debug);
            ProcessDeleteAllPosts(group);

            WallHelper.SetWall(group.Id, oldWall);

            CallbackHelper.SetCallback(group.Id, CallbackOperation.Wall, true);
        }
    }

    private static void ProcessDeleteAllPosts(IVkModel group)
    {
        try
        {
            var posts = VkFramework.GetAllPosts(group.Id).ToList();
            if (!posts.Any())
            {
                Logger.Log("Нет постов для удаления", LogType.Warning);
                return;
            }

            Logger.Log($"Количество постов: {posts.Count}");
            foreach (var post in posts) DeletePostInGroup(group.Id, post.Id);
        }
        catch (VkApiException e)
        {
            Logger.Log($"Не удалось получить посты сообщества {group.Id}");
            Logger.Log(e);
        }
    }

    private static void DeletePostInGroup(long group, long? post)
    {
        try
        {
            if (post == null) return;
            VkFramework.DeletePost(group, (long) post);
            Logger.Log($"Удалили пост {post} в сообществе {group}");
        }
        catch (VkApiException e)
        {
            Logger.Log($"Не удалось удалить пост {post} в сообществе {group}");
            Logger.Log(e);
        }
    }

    #endregion

    #region Misc

    private static void ProcessMisc(MiscParameters parameters)
    {
        switch (parameters.Type)
        {
            case MiscFunctionType.Stats:
                ProcessStats(Data.GroupList.Select(x => new Group {Id = x}).ToList());
                break;
            case MiscFunctionType.RemoveBanned:
                ProcessDeleteDogs(parameters.Groups ?? throw new InvalidOperationException());
                break;
            default:
                throw new ArgumentOutOfRangeException();
        }
    }

    private static void ProcessStats(IEnumerable<Group> groups)
    {
        var data = new List<GroupData>();
        foreach (var group in groups)
        {
            Logger.Log($"Обработка сообщества {group.Id}");
            data.Add(VkFramework.GetGroupData(group.Id));
        }

        Logger.Clear();
        var allManagers = data.SelectMany(x => x.Managers).ToList();
        var allUsers = data.SelectMany(x => x.AllUsers).ToList();
        var output =
            $"Вывод статистики\n\nСтатистика групп:\nВсего групп: {data.Count}\nСлоты под руководителей: {allManagers.Count}/{data.Count * 100}\n\n" +
            $"Статистика участников:\nВсего участников: {allUsers.Count}\nБез учета дубликатов: {allUsers.Select(x => x.Id).Distinct().Count()}\n" +
            $"Без учета заблокированных: {allUsers.Count(x => !x.IsDeactivated)}\n" +
            $"Без учета заблокированных и дубликатов: {allUsers.Where(x => !x.IsDeactivated).Select(x => x.Id).Distinct().Count()}\n\n" +
            $"Статистика руководителей:\nВсего руководителей: {allManagers.Count}\nБез учета дубликатов: {allManagers.Select(x => x.Id).Distinct().Count()}\n" +
            $"Без учета заблокированных: {allManagers.Count(x => !x.IsDeactivated)}\n" +
            $"Без учета заблокированных и дубликатов: {allManagers.Where(x => !x.IsDeactivated).Select(x => x.Id).Distinct().Count()}";
        Logger.Log(output);
    }

    private static void ProcessDeleteDogs(IEnumerable<Group> groups)
    {
        foreach (var group in groups)
        {
            Logger.Log($"Переходим к сообществу {group.Id}");
            var members = VkFramework.GetGroupData(group.Id);
            var bannedManagers = members.Managers.Where(member => member.IsDeactivated).ToList();

            if (!bannedManagers.Any()) Logger.Log("Собачек не было найдено", LogType.Warning);

            foreach (var manager in bannedManagers) DeleteDog(group.Id, manager.Id);
        }
    }

    private static void DeleteDog(long group, long user)
    {
        VkFramework.CaptchaSecondsToWait = 3600;
        try
        {
            VkFramework.EditManager(user, group, null);
            Logger.Log($"Сняли редактора {user} в сообществе {group}");
        }
        catch (VkApiException e)
        {
            Logger.Log($"Невозможно удалить {user} из сообщества {group}", LogType.Error);
            Logger.Log(e);
        }
    }

    #endregion
}
