using System.Diagnostics;
using nng_one.Logging;

namespace nng_one.Configs;

public static class ConfigDialog
{
    private const string TokenUrl =
        "https://oauth.vk.com/authorize?client_id=7436182&scope=270404&redirect_uri=https://oauth.vk.com/blank.html&display=page&response_type=token&revoke=1";

    private static readonly InputHandler InputHandler = InputHandler.GetInstance();

    public static void SetUpToken()
    {
        var config = ConfigProcessor.LoadConfig();
        var token = InputHandler.GetStringInput("Токен (введите «token», чтобы получить)", 4);
        while (token.ToLower() == "token")
        {
            Process.Start(new ProcessStartInfo {FileName = TokenUrl, UseShellExecute = true});
            token = InputHandler.GetStringInput("Токен");
        }

        config.Token = token;
        ConfigProcessor.SaveConfig(config);
    }

    private static void SetUpList()
    {
        var config = ConfigProcessor.LoadConfig();
        var data = InputHandler.GetStringInput("Общий список", 4);
        config.DataUrl = data;
        ConfigProcessor.SaveConfig(config);
    }

    private static void SetUpBanReason()
    {
        var config = ConfigProcessor.LoadConfig();
        var reason = InputHandler.GetStringInput("Причина блокировки", 0);
        config.BanReason = reason;
        ConfigProcessor.SaveConfig(config);
    }

    public static void SetUpConfig()
    {
        SetUpToken();
        SetUpList();
        SetUpBanReason();
    }
}
