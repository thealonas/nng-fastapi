namespace nng_one.Configs;

public class Config
{
    public Config(string token, string banReason, string dataUrl, bool captchaBypass, bool switchCallback, bool sentry)
    {
        Token = token;
        BanReason = banReason;
        DataUrl = dataUrl;
        CaptchaBypass = captchaBypass;
        SwitchCallback = switchCallback;
        Sentry = sentry;
    }

    public string Token { get; set; }
    public string BanReason { get; set; }
    public string DataUrl { get; set; }
    public bool CaptchaBypass { get; init; }
    public bool SwitchCallback { get; init; }
    public bool Sentry { get; init; }
}
