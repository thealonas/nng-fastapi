using System.Text;
using nng_one.Menu;
using nng.Enums;
using nng.Logging;

namespace nng_one.Logging;

public class InputHandler
{
    private static InputHandler? _instance;
    private static readonly Logger Logger = Program.Logger;

    private Message _annotationMessage = new(string.Empty, LogType.Error, forceSend: true);

    private InputHandler()
    {
    }

    public static InputHandler GetInstance()
    {
        return _instance ??= new InputHandler();
    }

    private void ProcessAnnotation()
    {
        if (_annotationMessage.IsEmpty()) return;

        Logger.Log(_annotationMessage);
        _annotationMessage = new Message(string.Empty, LogType.Error, forceSend: true);
    }

    private string RawInput(string userText)
    {
        ProcessAnnotation();
        Logger.Log($"{userText}: ", skipLine: false);
        var (left, top) = Console.GetCursorPosition();
        Console.SetCursorPosition(left, top);
        var input = Console.ReadLine();
        return input ?? string.Empty;
    }

    private string MenuRawInput(string menuText)
    {
        Logger.Clear(Program.Messages);
        ProcessAnnotation();
        Logger.Log("Выберете пункт меню:\n\n");
        Logger.Log(menuText, withoutTitle: true, withoutColor: true);
        var (left, top) = Console.GetCursorPosition();
        Console.Write(">");
        Console.SetCursorPosition(left + 1, top);
        var input = Console.ReadLine();
        return input ?? string.Empty;
    }

    private int GetIntInput(string userText, int minValue = -1, int maxValue = -1, bool isMenu = false,
        string? customError = null)
    {
        var needCorrection = !(minValue == -1 && maxValue == -1);
        while (true)
        {
            var input = isMenu ? MenuRawInput(userText) : RawInput(userText);

            if (!int.TryParse(input, out var result))
            {
                _annotationMessage.Text = "Необходимо указать число";
                continue;
            }

            if (!needCorrection) return result;

            if (result >= minValue && result <= maxValue) return result;
            _annotationMessage.Text = customError ??
                                      $"Необходимо указать значение в пределах от {minValue} до {maxValue}";
        }
    }

    public string GetStringInput(string userText, int minLen = 1)
    {
        while (true)
        {
            var input = RawInput(userText);
            if (input.Length < minLen)
                _annotationMessage.Text = $"Минимальная длина строки: {minLen}";
            else return input;
        }
    }

    public MainMenuItem GetMainMenuInput()
    {
        var userText = new StringBuilder();
        var menuItems = Enum.GetValues(typeof(MainMenuItem)).Cast<MainMenuItem>().ToList();
        foreach (var menu in menuItems) userText.AppendLine($"{menuItems.IndexOf(menu) + 1}. {menu.GetMenuItem()}\n");

        return (MainMenuItem) GetIntInput(userText.ToString(), 1, menuItems.Count, true);
    }

    public int GetMenuInput(IEnumerable<string> menus, out bool returnBack)
    {
        returnBack = false;
        var userText = new StringBuilder();
        var arguments = menus.ToList();
        arguments.Add("Вернуться назад");

        foreach (var argument in arguments) userText.AppendLine($"{arguments.IndexOf(argument) + 1}. {argument}\n");

        var input = GetIntInput(userText.ToString(), 1, arguments.Count, true) - 1;
        if (input + 1 == arguments.Count) returnBack = true;
        return input;
    }

    public bool GetBoolInput(string userText, string approveString = "Y", string declineString = "N")
    {
        while (true)
        {
            ProcessAnnotation();
            Logger.Log($"{userText} ({approveString}, {declineString}): ");
            var input = Console.ReadLine();
            if (input == null)
            {
                _annotationMessage.Text = $"({approveString}, {declineString})";
                continue;
            }

            if (string.Equals(input.Trim(), approveString.Trim(), StringComparison.CurrentCultureIgnoreCase))
                return true;
            if (string.Equals(input.Trim(), declineString.Trim(), StringComparison.CurrentCultureIgnoreCase))
                return false;
            _annotationMessage.Text = "Ввод не распознан";
        }
    }
}
