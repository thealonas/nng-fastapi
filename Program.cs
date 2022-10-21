using System.Reflection;
using System.Text;
using Microsoft.Extensions.DependencyInjection;
using nng_one.Configs;
using nng_one.Exceptions;
using nng_one.Helpers;
using nng_one.ServiceCollections;
using nng.Enums;
using nng.Helpers;
using nng.Logging;
using nng.Services;
using nng.VkFrameworks;
using Sentry;

namespace nng_one;

public static class CommandLineArguments
{
    public const string DebugMode = "debug";
}

public static class Program
{
    public static readonly Version Version =
        Assembly.GetExecutingAssembly().GetName().Version ?? throw new InvalidOperationException();

    public static readonly List<Message> Messages = new();
    public static readonly Logger Logger = new(new ProgramInformationService(Version, false), "nng one");
    public static bool DebugMode { get; private set; }
    private static bool SentryEnabled { get; set; }

    private static void CommandLineProcessor(IEnumerable<string> list)
    {
        var strings = list.Select(x => x.Replace("--", string.Empty));
        foreach (var commandLine in strings)
            if (commandLine.ToLower().Trim() == CommandLineArguments.DebugMode)
                DebugMode = true;
    }

    private static void Main(string[] args)
    {
        if (args is {Length: > 0}) CommandLineProcessor(args);
        var windows = OperatingSystem.IsWindows();

        var debug = DebugMode ? " debug" : string.Empty;
        Console.Title = $"nng one v{Version.Major}.{Version.Minor}{debug}";

        Console.InputEncoding = windows ? Encoding.Unicode : Encoding.UTF8;
        Console.OutputEncoding = windows ? Encoding.Unicode : Encoding.Default;

        Console.CancelKeyPress += delegate { Console.ResetColor(); };
        Console.ResetColor();

        using (SentrySdk.Init(o =>
               {
                   o.Dsn = "https://ca8c3bff58144b4ca6d677ee5c80b376@o555933.ingest.sentry.io/5905813";
                   o.Environment = "dev";
               }))
        {
            while (true)
                try
                {
                    var exit = false;
                    while (!exit) exit = SetUp();
                    while (true) Startup.Start();
                }
                catch (Exception e)
                {
                    Logger.Log(e);
                    Logger.Log($"stacktrace: {e.StackTrace}", LogType.Error);
                    if (SentryEnabled) SentrySdk.CaptureException(e);
                    Logger.Idle();
                }
        }
        // ReSharper disable once FunctionNeverReturns
    }

    private static bool SetUp()
    {
        Console.Clear();

        Config config;

        var info = new ProgramInformationService(Version, DebugMode);
        var logger = new Logger(info, "nng one");
        var collectionBuilder = new ServiceCollectionBuilder();

        try
        {
            config = ConfigProcessor.LoadConfig();
        }
        catch (ConfigNotFoundException)
        {
            config = new Config(string.Empty, string.Empty, string.Empty, false, true, true);
            ConfigProcessor.SaveConfig(config);
        }

        if (config.Token.Length < 1)
        {
            logger.Clear();
            ConfigDialog.SetUpConfig();
            return false;
        }

        VkFramework framework;
        try
        {
            framework = new VkFramework(config.Token);
        }
        catch (Exception)
        {
            logger.Log("Недействительный токен", LogType.Error);
            ConfigDialog.SetUpToken();
            return false;
        }

        VkFramework.OnCaptchaWait += delegate(object? _, CaptchaEventArgs time)
        {
            logger.Log($"Каптча, ожидаем {time.SecondsToWait} секунд");
        };

        if (!config.CaptchaBypass) framework.SetCaptchaSolver(new CaptchaHandler());
        else framework.ResetCaptchaSolver();

        var currentUser = framework.CurrentUser;

        Messages.Add(new Message($"Добро пожаловать, {currentUser.FirstName} | Ваш ID: {currentUser.Id}",
            LogType.InfoVersionShow));

        if (UpdateHelper.IfUpdateNeed(out var version))
            Messages.Add(new Message(
                $"Версия v{Version.Major}.{Version.Minor} устарела, пожалуйста, обновитесь до {version}",
                LogType.Debug, forceSend: true));

        SentryEnabled = config.Sentry;

        collectionBuilder.Configure(() =>
        {
            var sc = new ServiceCollection();
            sc.AddSingleton(DataHelper.GetDataAsync(config.DataUrl).GetAwaiter().GetResult());
            sc.AddSingleton(info);
            sc.AddSingleton(logger);
            sc.AddSingleton(config);
            sc.AddSingleton(framework);
            sc.AddSingleton(new CallbackHelper(framework, new LoggerWrapper(logger)));
            return sc;
        });

        ServiceCollectionContainer.Initialize(collectionBuilder.Build());
        return true;
    }
}
