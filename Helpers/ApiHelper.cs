using nng_one.Models;
using JsonSerializer = System.Text.Json.JsonSerializer;

namespace nng_one.Helpers;

public static class ApiHelper
{
    private static readonly HttpClient HttpClient = new();

    private static async Task<T> SendRequest<T>(string url)
    {
        var response = await HttpClient.SendAsync(new HttpRequestMessage
        {
            RequestUri = new Uri(url)
        });

        response.EnsureSuccessStatusCode();

        var output = JsonSerializer.Deserialize<T>(await response.Content.ReadAsStringAsync());

        return output ?? throw new InvalidOperationException("Data was not retrieved");
    }

    public static ApiData GetApiData(string groupUrl, string bnndUrl)
    {
        var groups = SendRequest<List<ApiGroup>>(groupUrl).GetAwaiter().GetResult();
        var users = SendRequest<List<User>>(bnndUrl).GetAwaiter().GetResult();

        return new ApiData(groups, users);
    }
}
