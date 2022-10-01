using Microsoft.Extensions.DependencyInjection;

namespace nng_one.ServiceCollections;

public class ServiceCollectionBuilder
{
    private IServiceCollection? _serviceProvider;

    public ServiceCollectionBuilder Configure(Func<IServiceCollection> configureServices)
    {
        _serviceProvider = configureServices();
        return this;
    }

    public IServiceProvider Build()
    {
        return _serviceProvider?.BuildServiceProvider() ?? throw new InvalidOperationException();
    }
}
