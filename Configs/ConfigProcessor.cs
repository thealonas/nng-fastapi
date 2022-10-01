using Newtonsoft.Json;
using nng_one.Exceptions;

namespace nng_one.Configs;

public static class ConfigProcessor
{
    private const string ConfigFileName = "config.json";

    public static Config LoadConfig()
    {
        if (!File.Exists(ConfigFileName)) throw new ConfigNotFoundException("Конфиг не найден");
        return JsonConvert.DeserializeObject<Config>(File.ReadAllText(ConfigFileName)) ??
               throw new InvalidOperationException();
    }

    public static void SaveConfig(Config config)
    {
        File.WriteAllText(ConfigFileName, JsonConvert.SerializeObject(config, Formatting.Indented));
    }
}
