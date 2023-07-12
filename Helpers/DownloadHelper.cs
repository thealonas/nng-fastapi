using System.Net.Http.Headers;
using System.Text;

namespace nng_one.Helpers;

public static class DownloadHelper
{
    private static readonly HttpClient Client = new();

    public static string UploadFile(string serverUrl, byte[] file, string fileExtension)
    {
        var requestContent = FormContent(file, fileExtension);
        return PostAndReturnResponse(serverUrl, requestContent);
    }

    public static string UploadFile(string serverUrl, byte[] file, string fileExtension, int x, int y, int w)
    {
        var requestContent = FormContent(file, fileExtension);
        requestContent.Add(new StringContent($"{x},{y},{w}"), "_square_crop");
        return PostAndReturnResponse(serverUrl, requestContent);
    }

    private static MultipartFormDataContent FormContent(byte[] file, string fileExtension)
    {
        var requestContent = new MultipartFormDataContent();
        var content = new ByteArrayContent(file);
        content.Headers.ContentType = MediaTypeHeaderValue.Parse("multipart/form-data");
        requestContent.Add(content, "file", $"file.{fileExtension}");
        return requestContent;
    }

    private static string PostAndReturnResponse(string serverUrl, HttpContent content)
    {
        var response = Client.PostAsync(serverUrl, content).GetAwaiter().GetResult();
        return Encoding.Default.GetString(response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult());
    }

    public static byte[] DownloadFile(string url)
    {
        var content = Client.GetByteArrayAsync(url).GetAwaiter().GetResult();
        return content;
    }
}
