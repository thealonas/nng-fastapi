using nng_one.Configs;
using nng_one.FunctionParameters;
using nng_one.Input;
using nng_one.Interfaces;
using nng_one.Models;
using nng_one.ServiceCollections;
using nng.Logging;
using VkNet.Model;
using User = VkNet.Model.User;

namespace nng_one.Menu;

public class Menu
{
    private readonly Config _config = ConfigProcessor.LoadConfig();
    private readonly ApiData _data = ServiceCollectionContainer.GetInstance().Data;
    private readonly InputHandler _inputHandler = InputHandler.GetInstance();
    private readonly Logger _logger = ServiceCollectionContainer.GetInstance().GlobalLogger;

    public IFunctionParameter GetResult()
    {
        _logger.Clear(Program.Messages);
        return _inputHandler.GetMainMenuInput() switch
        {
            MainMenuItem.Block => Block(),
            MainMenuItem.Unblock => Unblock(),
            MainMenuItem.Editors => Editors(),
            MainMenuItem.Search => Search(),
            MainMenuItem.Misc => Misc(),
            _ => throw new ArgumentOutOfRangeException()
        };
    }

    private IFunctionParameter Block()
    {
        if (_inputHandler.GetBoolInput("Начать блокировку пользователей в сообществах?"))
            return new BlockParameters(_data.Users.Where(x => x.Banned).Select(x => x.UserId),
                _data.Groups.Select(x => x.GroupId), _config);

        _logger.Clear();
        return GetResult();
    }

    private IFunctionParameter Unblock()
    {
        var userChoice = _inputHandler.GetMenuInput(new[] { "Пользователя", "Пользователей" }, out var returnBack);
        if (returnBack)
        {
            _logger.Clear();
            return GetResult();
        }

        var users = userChoice == 0
            ? VkUserInput.GetUserInput().ToList()
            : null;

        var groupChoice =
            _inputHandler.GetMenuInput(new[] { "В сообществе", "В сообществах" }, out var groupReturnBack);
        if (groupReturnBack)
        {
            _logger.Clear();
            return Unblock();
        }

        var groups = groupChoice == 0
            ? VkUserInput.GetGroupInput().ToList()
            : _data.Groups.Select(x => new Group { Id = x.GroupId }).ToList();

        return new UnblockParameters(_config, groups, users);
    }

    private IFunctionParameter Editors()
    {
        var giveChoice = _inputHandler.GetMenuInput(new[] { "Выдача", "Снятие" }, out var returnBack) == 0
            ? EditorOperationType.Give
            : EditorOperationType.Fire;
        if (returnBack)
        {
            _logger.Clear();
            return GetResult();
        }

        List<User>? users = null;

        var userChoice = _inputHandler.GetMenuInput(new[] { "Пользователю", "Пользователям" }, out var userReturnBack);
        if (userReturnBack)
        {
            _logger.Clear();
            return Editors();
        }

        if (userChoice == 0)
        {
            users = VkUserInput.GetUserInput().ToList();
            return new EditorParameters(giveChoice, _config, users,
                _data.Groups.Select(x => new Group { Id = x.GroupId }));
        }

        var groupChoice =
            _inputHandler.GetMenuInput(new[] { "В сообществе", "В сообществах" }, out var groupReturnBack);
        if (groupReturnBack)
        {
            _logger.Clear();
            return Editors();
        }

        if (groupChoice == 1)
        {
            var phrase = giveChoice == EditorOperationType.Give ? "выдать" : "снять";
            if (!_inputHandler.GetBoolInput($"Вы уверены, что хотите {phrase} редактора пользователям в сообществах?"))
                return Editors();
        }

        var groupList = groupChoice == 0
            ? VkUserInput.GetGroupInput().ToList()
            : _data.Groups.Select(x => new Group { Id = x.GroupId }).ToList();

        return new EditorParameters(giveChoice, _config, users, groupList);
    }

    private IFunctionParameter Search()
    {
        var funcChoose = _inputHandler.GetMenuInput(new[]
        {
            "Редактора",
            "Несостыковок"
        }, out var returnBack);

        if (returnBack)
        {
            _logger.Clear();
            return GetResult();
        }

        switch (funcChoose)
        {
            case 0:
                var user = VkUserInput.GetUserInput();
                var groups = _data.Groups.Select(x => new Group { Id = x.GroupId });
                return new SearchParameters(user, groups, _config);
            case 1:
                if (!_inputHandler.GetBoolInput("Вы уверены, что хотите посмотреть несостыковки?"))
                    return Search();
                return new BanCompareParameters(_data.Groups.Select(x => x.GroupId).ToList(), _data.Users
                    .Where(x => x.Banned).Select(x => x.UserId), _config);
            default:
                throw new ArgumentOutOfRangeException();
        }
    }

    private IFunctionParameter Misc()
    {
        var funcChoice = _inputHandler.GetMenuInput(new[]
        {
            "Репост записи", "Репост истории",
            "Удаление всех записей со стены", "Статистика",
            "Снятие собачек", "Создание сообщества", "Удаление неактивных редакторов"
        }, out var returnBack);
        if (returnBack)
        {
            _logger.Clear();
            return GetResult();
        }

        switch (funcChoice)
        {
            case 0:
                var post = VkUserInput.GetPostInput();
                return new GroupWallParameters(_config, GroupWallParametersType.Repost,
                    _data.Groups.Select(x => new Group { Id = x.GroupId }), post);
            case 1:
                var story = _inputHandler.GetStringInput("Введите ссылку на пост", 4);
                var groups = _data.Groups.Select(x => new Group { Id = x.GroupId });
                return new MiscParameters(_config, MiscFunctionType.RepostStories, groups, story, null);
            case 2:
                if (!_inputHandler.GetBoolInput("Вы уверены, что хотите удалить все записи со стены?"))
                    return Misc();
                return new GroupWallParameters(_config, GroupWallParametersType.DeleteAllPosts,
                    _data.Groups.Select(x => new Group { Id = x.GroupId }), null);
            case 3:
                return new MiscParameters(_config, MiscFunctionType.Stats, null, null, null);
            case 4:
                return new MiscParameters(_config, MiscFunctionType.RemoveBanned,
                    _data.Groups.Select(x => new Group { Id = x.GroupId }), null, null);
            case 5:
                var shortName = _inputHandler.GetStringInput("Введите короткую ссылку", 2);
                return new MiscParameters(_config, MiscFunctionType.CreateCommunity, null, null,
                    shortName);
            case 6:
                if (!_inputHandler.GetBoolInput(
                        "Вы уверены, что хотите снять всех неактивных редакторов во всех группах?"))
                    return Misc();
                var targetGroups = _data.Groups.Select(x => new Group { Id = x.GroupId });
                return new MiscParameters(_config, MiscFunctionType.Revoke, targetGroups, null, string.Empty);
            default:
                throw new ArgumentOutOfRangeException();
        }
    }
}
