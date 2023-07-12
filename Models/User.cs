using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using nng_one.Enums;

namespace nng_one.Models;

public class User
{
    /// <summary>
    ///     Имя и фамилия на момент появления у нас
    /// </summary>
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    /// <summary>
    ///     Айди страинцы
    /// </summary>
    [JsonPropertyName("user_id")]
    public long UserId { get; set; }

    /// <summary>
    ///     Является ли пользователь администратором
    /// </summary>
    [JsonPropertyName("admin")]
    public bool Admin { get; set; }

    /// <summary>
    ///     Находится ли пользователь в списке приоритетных
    /// </summary>
    [JsonPropertyName("thx")]
    public bool Thanks { get; set; }

    /// <summary>
    ///     Пользовался ли человек ботом или приложением
    /// </summary>
    [JsonPropertyName("app")]
    public bool App { get; set; }

    /// <summary>
    ///     Список групп, в которых пользователь редактор
    /// </summary>
    [JsonPropertyName("groups")]
    public List<long>? Groups { get; set; }

    /// <summary>
    ///     Заблокирован ли пользователь на данный момент
    /// </summary>
    [JsonPropertyName("bnnd")]
    public bool Banned { get; set; }

    /// <summary>
    ///     Информация о нарушении правил (остаётся даже если человек был разблокирован)
    /// </summary>
    [JsonPropertyName("bnnd_info")]
    public JsonObject? BannedInfo { get; set; }
}
