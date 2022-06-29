using Newtonsoft.Json;
using nng_one.Logging;

namespace nng_one.Helpers;

public struct GithubUpdate
{
    public GithubUpdate(string? newVersion)
    {
        NewVersion = newVersion;
    }

    [JsonProperty("tag_name")] public string? NewVersion;
}

public static class UpdateHelper
{
    private const string ApiUrl = "https://api.github.com/repos/MrAlonas/nng-one/releases/latest";

    public static bool IfUpdateNeed(out string version)
    {
        version = string.Empty;
        try
        {
            var client = new HttpClient();
            client.DefaultRequestHeaders.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)");

            var webResponse = client.GetAsync(ApiUrl).Result;
            var response = webResponse.Content.ReadAsStringAsync().Result;
            var data = JsonConvert.DeserializeObject<GithubUpdate>(response);

            if (data.NewVersion == null) return false;

            var newVersion = new string(data.NewVersion.Where(char.IsDigit).ToArray());
            var ver = Program.Version;
            var currentVersion = int.Parse($"{ver.Major}{ver.Minor}");

            if (int.Parse(newVersion) <= currentVersion) return false;

            version = data.NewVersion;
            return true;
        }
        catch (Exception e)
        {
            Logger.Log(e);
            return false;
        }
    }
}
