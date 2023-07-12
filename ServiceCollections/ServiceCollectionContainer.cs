using nng_one.Extensions;
using nng_one.Models;
using nng.Helpers;
using nng.Logging;
using nng.Models;
using nng.VkFrameworks;

namespace nng_one.ServiceCollections;

public class ServiceCollectionContainer
{
    private static ServiceCollectionContainer? _instance;

    private ServiceCollectionContainer(IServiceProvider provider)
    {
        ServiceProvider = provider;
    }

    private IServiceProvider ServiceProvider { get; }

    public Logger GlobalLogger => ServiceProvider.ForceGetService<Logger>();
    public VkFramework VkFramework => ServiceProvider.ForceGetService<VkFramework>();
    public CallbackHelper CallbackHelper => ServiceProvider.ForceGetService<CallbackHelper>();
    public ApiData Data => ServiceProvider.ForceGetService<ApiData>();

    public static void Initialize(IServiceProvider provider)
    {
        _instance = new ServiceCollectionContainer(provider);
    }

    public static ServiceCollectionContainer GetInstance()
    {
        return _instance ?? throw new InvalidOperationException();
    }
}
