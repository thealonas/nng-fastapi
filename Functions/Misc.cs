using System.Net.Http.Headers;
using System.Text;
using Newtonsoft.Json.Linq;
using nng_one.FunctionParameters;
using nng_one.Helpers;
using nng_one.Interfaces;
using nng_one.ServiceCollections;
using nng.Enums;
using nng.Helpers;
using nng.Logging;
using nng.Models;
using nng.VkFrameworks;
using Sentry;
using VkNet.Enums;
using VkNet.Exception;
using VkNet.Model;
using VkNet.Model.RequestParams.Stories;
using VkNet.Utils;
using CaptchaHandler = nng_one.Helpers.CaptchaHandler;
using Constants = nng.Constants.Constants;

namespace nng_one.Functions;

public static class Misc
{
    private static readonly VkFramework VkFramework = ServiceCollectionContainer.GetInstance().VkFramework;
    private static readonly DataModel Data = ServiceCollectionContainer.GetInstance().Data;
    private static readonly Logger Logger = ServiceCollectionContainer.GetInstance().GlobalLogger;
    private static readonly CallbackHelper CallbackHelper = ServiceCollectionContainer.GetInstance().CallbackHelper;

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
            case MiscFunctionType.RepostStories:
                ProcessRepostStories(parameters.Groups ?? throw new InvalidOperationException(),
                    parameters.StoryUrl ?? throw new InvalidOperationException());
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
        VkFramework.CaptchaSecondsToWait = Constants.CaptchaEditorWaitTime;
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

    private static void ProcessRepostStories(IEnumerable<Group> groups, string url)
    {
        using var client = new HttpClient();
        var bytes = File.ReadAllBytes("story.jpg");
        var toSave = new List<string>();

        foreach (var group in groups)
        {
            Logger.Log($"Обрабатываем сообщество {group.Id}");

            var uploadResult = VkFrameworkExecution.ExecuteWithReturn(() =>
                VkFramework.Api.Stories.GetPhotoUploadServer(new GetPhotoUploadServerParams
                {
                    LinkUrl = url,
                    GroupId = (ulong) group.Id,
                    AddToNews = true
                }));

            Logger.Log($"Получили ссылку на загрузку: {uploadResult.UploadUrl}, посылаем POST-запрос…", LogType.Debug);

            try
            {
                var result = JObject.Parse(UploadFile(uploadResult.UploadUrl.ToString(), bytes, "jpg"));
                var response = result["response"] ?? throw new NullReferenceException();
                var serverUploadResult = response["upload_result"] ?? throw new NullReferenceException();

                toSave.Add(serverUploadResult.ToString());
            }
            catch (Exception e)
            {
                SentrySdk.CaptureException(e);
                Logger.Log($"Ошибка при публикации истории: {e.GetType()}: {e.Message}", LogType.Error);
            }
        }

        Logger.Log("Сохраняем истории…");
        foreach (var server in toSave)
            VkFrameworkExecution.Execute(() => VkFramework.Api.Call("stories.save", new VkParameters
            {
                {"upload_results", server}
            }));
    }

    private static string UploadFile(string serverUrl, byte[] file, string fileExtension)
    {
        using var client = new HttpClient();
        var requestContent = new MultipartFormDataContent();
        var content = new ByteArrayContent(file);
        content.Headers.ContentType = MediaTypeHeaderValue.Parse("multipart/form-data");
        requestContent.Add(content, "file", $"file.{fileExtension}");

        var response = client.PostAsync(serverUrl, requestContent).GetAwaiter().GetResult();
        return Encoding.Default.GetString(response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult());
    }

    #endregion
}
