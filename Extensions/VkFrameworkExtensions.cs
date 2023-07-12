using nng_one.CaptchaSolver;
using nng_one.Configs;
using nng_one.Helpers;
using nng.VkFrameworks;

namespace nng_one.Extensions;

public static class VkFrameworkExtensions
{
    private static readonly Config Config = ConfigProcessor.LoadConfig();

    public static void SetCaptchaBasedOnConfig(this VkFramework vkFramework)
    {
        if (!Config.CaptchaBypass)
        {
            vkFramework.SetCaptchaSolver(new CaptchaHandler());
        }
        else
        {
            if (!string.IsNullOrEmpty(Config.RuCaptchaToken) && !string.IsNullOrWhiteSpace(Config.RuCaptchaToken))
                vkFramework.SetCaptchaSolver(new RuCaptchaSolver(Config.RuCaptchaToken));
            else
                vkFramework.ResetCaptchaSolver();
        }
    }
}
