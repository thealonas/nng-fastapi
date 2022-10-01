using nng_one.Controllers;
using nng_one.ServiceCollections;
using nng.Logging;

namespace nng_one;

public static class Startup
{
    private static readonly Logger Logger = ServiceCollectionContainer.GetInstance().GlobalLogger;

    public static void Start()
    {
        Logger.Clear(Program.Messages);
        var menu = new Menu.Menu().GetResult();
        FunctionController.ProcessFunction(menu);
    }
}
