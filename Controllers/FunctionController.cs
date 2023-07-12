using nng_one.Extensions;
using nng_one.FunctionParameters;
using nng_one.Functions;
using nng_one.Interfaces;
using nng_one.ServiceCollections;
using nng.Enums;
using nng.Logging;
using nng.VkFrameworks;

namespace nng_one.Controllers;

public static class FunctionController
{
    private static readonly VkFramework VkFramework = ServiceCollectionContainer.GetInstance().VkFramework;
    private static readonly Logger Logger = ServiceCollectionContainer.GetInstance().GlobalLogger;

    public static void ProcessFunction(IFunctionParameter parameter)
    {
        VkFramework.SetCaptchaBasedOnConfig();
        Logger.Clear();
        switch (parameter)
        {
            case BlockParameters blockParameters:
                Block.Process(blockParameters);
                break;
            case UnblockParameters unblockParameters:
                Unblock.Process(unblockParameters);
                break;
            case EditorParameters editorParameters:
                Editor.Process(editorParameters);
                break;
            case MiscParameters miscParameters:
                Misc.Process(miscParameters);
                break;
            case GroupWallParameters groupWallParameters:
                Misc.Process(groupWallParameters);
                break;
            case SearchParameters searchParameters:
                Search.Process(searchParameters);
                break;
            case BanCompareParameters banCompareParameters:
                BanCompare.Process(banCompareParameters);
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(parameter), parameter, null);
        }

        Logger.Log("Операция завершена", LogType.Warning);
        Logger.Idle();
    }
}
