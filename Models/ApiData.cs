namespace nng_one.Models;

public class ApiData
{
    public readonly List<ApiGroup> Groups;
    public readonly List<User> Users;

    public ApiData(List<ApiGroup> groups, List<User> users)
    {
        Groups = groups;
        Users = users;
    }
}
