namespace nng_one.Extensions;

public static class ServiceProviderExtensions
{
    public static bool TryGetService<T>(this IServiceProvider provider, out T service)
    {
        service = default!;
        try
        {
            service = (T)(provider.GetService(typeof(T)) ?? throw new InvalidOperationException());
            return true;
        }
        catch (Exception)
        {
            return false;
        }
    }

    public static T ForceGetService<T>(this IServiceProvider provider)
    {
        return (T)(provider.GetService(typeof(T)) ?? throw new InvalidOperationException());
    }
}
