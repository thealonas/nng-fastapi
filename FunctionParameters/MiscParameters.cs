using nng_one.Configs;
using nng_one.Interfaces;
using VkNet.Model;

namespace nng_one.FunctionParameters;

public enum MiscFunctionType
{
    Stats,
    RepostStories,
    RemoveBanned,
    CreateCommunity,
    Revoke
}

public class MiscParameters : IFunctionParameter
{
    public MiscParameters(Config config, MiscFunctionType type, IEnumerable<Group>? groups, string? storyUrl,
        string? shortName)
    {
        Config = config;
        Type = type;
        Groups = groups;
        StoryUrl = storyUrl;
        ShortName = shortName;
    }

    public MiscFunctionType Type { get; }
    public IEnumerable<Group>? Groups { get; }

    public string? StoryUrl { get; }

    public string? ShortName { get; }

    public Config Config { get; }
}
