namespace nng_one.Configs;

public class Config
{
    public Config(string token, string ruCaptchaToken, string banReason, bool captchaBypass, bool switchCallback,
        bool sentry,
        string bnndUrl, string groupsUrl)
    {
        Token = token;
        RuCaptchaToken = ruCaptchaToken;
        BanReason = banReason;
        CaptchaBypass = captchaBypass;
        SwitchCallback = switchCallback;
        Sentry = sentry;
        BnndUrl = bnndUrl;
        GroupsUrl = groupsUrl;
    }

    public string Token { get; set; }
    public string RuCaptchaToken { get; set; }
    public string BanReason { get; set; }
    public string BnndUrl { get; set; }
    public string GroupsUrl { get; set; }
    public bool CaptchaBypass { get; init; }
    public bool SwitchCallback { get; init; }
    public bool Sentry { get; init; }
}
