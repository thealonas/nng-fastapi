using System.Text;
using Newtonsoft.Json.Linq;
using nng_one.Helpers;
using nng_one.Input;
using nng_one.ServiceCollections;
using nng.Enums;
using nng.Logging;
using nng.VkFrameworks;
using VkNet.Model;
using VkNet.Model.RequestParams;
using VkNet.Utils;
using CaptchaHandler = nng_one.Helpers.CaptchaHandler;

namespace nng_one.Functions;

public static class CreateCommunity
{
    private const string CoverUrl = "https://nng.alonas.ml/assets/images/style/cover/png/main.png";
    private const string LogoUrl = "https://nng.alonas.ml/assets/images/style/logo/png/main.png";
    private const string Status = "редактор после 50 и 100 подписчиков (или через бота)";
    private const string CommunityName = "ฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺฺ";
    private static readonly VkFramework VkFramework = ServiceCollectionContainer.GetInstance().VkFramework;
    private static readonly Logger Logger = ServiceCollectionContainer.GetInstance().GlobalLogger;
    private static readonly InputHandler InputHandler = InputHandler.GetInstance();

    public static void Create(string shortName)
    {
        VkFramework.SetCaptchaSolver(new CaptchaHandler());

        Logger.Log("Начинаем создание сообщества…");

        var group = VkFrameworkExecution.ExecuteWithReturn(() => VkFramework.Api.Groups.Create(
            CommunityName,
            "Комментируем от имени групп.\n\nРедактор выдаётся через бота — vk.me/nngbot" +
            "\n\nНаши правила — vk.com/@mralonas-nng-rules\n\nFAQ — vk.com/@mralonas-nng-faq"));

        Logger.Log($"Сообщество {group.Id} создано");

        VkFrameworkExecution.Execute(() =>
        {
            VkFramework.Api.Call("groups.edit", new VkParameters(new Dictionary<string, string>
            {
                { "group_id", group.Id.ToString() },
                { "address", shortName },
                { "public_category", "1001" },
                { "public_subcategory", "3016" },

                { "main_section", "0" },
                { "secondary_section", "0" },
                { "wall", "2" },
                { "topics", "0" },
                { "photos", "0" },
                { "audio", "0" },
                { "video", "0" },
                { "events", "0" },
                { "places", "0" },
                { "articles", "0" },
                { "addresses", "0" },
                { "docs", "0" },
                { "wiki", "0" },

                { "clips", "0" },
                { "narratives", "0" },
                { "recognize_photo", "0" },
                { "textlives", "0" },

                { "website", "https://nng.alonas.ml" }
            }));
        });

        Logger.Log("Сообщество настроено");

        try
        {
            UploadCover(group.Id);
            Logger.Log("Обложка загружена");
        }
        catch (Exception e)
        {
            Logger.Log(e);
        }

        try
        {
            UploadLogo(group.Id);
            Logger.Log("Аватарка загружена");
        }
        catch (Exception e)
        {
            Logger.Log(e.Message);
        }

        AddLinks(group.Id);
        Logger.Log("Ссылки добавлены");

        SetStatus(group.Id);
        Logger.Log("Статус установлен");

        AddWatchdog(group.Id);
        Logger.Log("Ватчдог добавлен");

        Logger.Log($"Создание сообщества завершено!\n\nhttps://vk.com/club{group.Id}");
    }

    private static void UploadCover(long group)
    {
        var cover = DownloadHelper.DownloadFile(CoverUrl);
        var coverUploadServer = VkFrameworkExecution.ExecuteWithReturn(() =>
            VkFramework.Api.Photo.GetOwnerCoverPhotoUploadServer(group, 0, 0, 1920, 768));

        var result = JObject.Parse(DownloadHelper.UploadFile(coverUploadServer.UploadUrl, cover, "png"));

        var hash = result["hash"] ?? throw new InvalidOperationException();
        var photo = result["photo"] ?? throw new InvalidOperationException();

        VkFrameworkExecution.Execute(() =>
        {
            VkFramework.Api.Call("photos.saveOwnerCoverPhoto", new VkParameters(new Dictionary<string, string>
            {
                { "hash", hash.ToString() },
                { "photo", photo.ToString() }
            }));
        });
    }

    private static void UploadLogo(long group)
    {
        var logo = DownloadHelper.DownloadFile(LogoUrl);
        var photoUploadServer =
            VkFrameworkExecution.ExecuteWithReturn(() => VkFramework.Api.Photo.GetOwnerPhotoUploadServer(-group));

        var result = JObject.Parse(DownloadHelper.UploadFile(photoUploadServer.UploadUrl, logo, "png",
            5000, 5000, 5000));

        var hash = result["hash"] ?? throw new InvalidOperationException();
        var photo = result["photo"] ?? throw new InvalidOperationException();
        var server = result["server"] ?? throw new InvalidOperationException();

        var saveResult = VkFrameworkExecution.ExecuteWithReturn(() =>
            VkFramework.Api.Call("photos.saveOwnerPhoto", new VkParameters(new Dictionary<string, string>
            {
                { "hash", hash.ToString() },
                { "photo", photo.ToString() },
                { "server", server.ToString() }
            })));

        var postId = long.Parse((saveResult["post_id"] ?? throw new InvalidOperationException()).ToString());

        VkFramework.DeletePost(group, postId);
    }

    private static void AddLinks(long group)
    {
        VkFrameworkExecution.Execute(() =>
        {
            VkFramework.Api.Groups.AddLink(group, new Uri("https://vk.com/nngbot"), "Бот для выдачи «редактора»");
        });

        VkFrameworkExecution.Execute(() =>
        {
            VkFramework.Api.Groups.AddLink(group, new Uri("https://vk.com/mralonas"), "Основная группа");
        });
    }

    private static void AddWatchdog(long group)
    {
        var secret = GenerateSecretKey();

        var confirm =
            VkFrameworkExecution.ExecuteWithReturn(() =>
                VkFramework.Api.Groups.GetCallbackConfirmationCode((ulong)group));

        Logger.Log("Добавьте следующую конфигурацию в настройки nng watchdog:");
        Logger.Log($"\"{group}\": " + "{\n  \"Confirm\": \"" + confirm + "\",\n  \"Secret\": \"" + secret + "\"\n}\n",
            LogType.Warning, withoutTitle: true);

        var url = InputHandler.GetStringInput("Введите ссылку на сервер");

        VkFrameworkExecution.Execute(() =>
        {
            VkFramework.Api.Groups.EditCallbackServer((ulong)group, 1, url, "watchdog", secret);
        });

        VkFrameworkExecution.Execute(() =>
        {
            VkFramework.Api.Groups.SetCallbackSettings(new CallbackServerParams
            {
                GroupId = (ulong?)group,
                ServerId = 1,
                CallbackSettings = new CallbackSettings
                {
                    PhotoNew = true,
                    WallPostNew = true,
                    WallRepost = true,
                    GroupLeave = true,
                    UserBlock = true,
                    UserUnblock = true,
                    GroupChangePhoto = true
                }
            });
        });
    }

    private static void SetStatus(long group)
    {
        VkFramework.SetGroupStatus(group, Status);
    }

    private static string GenerateSecretKey(int lenght = 20)
    {
        var symbols = new[]
        {
            "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q",
            "r", "s", "t", "u", "v", "w", "x", "y", "z", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"
        };

        var random = new Random();
        var result = new StringBuilder();

        for (var i = 0; i < lenght; i++)
        {
            var targetSymbol = symbols[random.Next(0, symbols.Length)];

            if (random.Next(0, 2) == 1) targetSymbol = targetSymbol.ToUpper();

            result.Append(targetSymbol);
        }

        return result.ToString();
    }
}
