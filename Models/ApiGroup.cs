using System.Text.Json.Serialization;

namespace nng_one.Models;

public class ApiGroup
{
    [JsonPropertyName("group_id")] public long GroupId { get; set; }

    [JsonPropertyName("screen_name")] public string ScreenName { get; set; } = string.Empty;
}
