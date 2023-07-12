using nng_one.ServiceCollections;
using nng.Enums;
using nng.Logging;
using TwoCaptcha.Captcha;
using VkNet.Utils.AntiCaptcha;

namespace nng_one.CaptchaSolver;

public class RuCaptchaSolver : ICaptchaSolver
{
    private readonly TwoCaptcha.TwoCaptcha _twoCaptcha;
    private readonly HttpClient _httpClient;

    private readonly Logger _logger = ServiceCollectionContainer.GetInstance().GlobalLogger;

    private string _lastCaptchaId = "";
    private bool _lastCaptchaReported;

    public RuCaptchaSolver(string apiKey)
    {
        _httpClient = new HttpClient();
        _twoCaptcha = new TwoCaptcha.TwoCaptcha(apiKey);
        _lastCaptchaReported = true;
    }

    public string Solve(string url)
    {
        if (!_lastCaptchaReported && !string.IsNullOrEmpty(_lastCaptchaId))
        {
            _logger.Log("Положительный репорт с ID отослан", LogType.Debug);
            _twoCaptcha.Report(_lastCaptchaId, true);
            _lastCaptchaReported = true;
        }

        DownloadCaptcha(url);

        _logger.Log("Решаем капчту...");
        var normal = new Normal("temp/captcha.jpg");

        try
        {
            _twoCaptcha.Solve(normal).GetAwaiter().GetResult();
        }
        catch (Exception e)
        {
            _logger.Log($"Не удалось решить каптчу {normal.Id}: {e.GetType()}: {e.Message}", LogType.Error);
            _lastCaptchaId = normal.Id;
            _lastCaptchaReported = false;
            return string.Empty;
        }

        _lastCaptchaId = normal.Id;
        _lastCaptchaReported = false;

        _logger.Log($"Ответ RuCaptcha: {normal.Code} | ID: {normal.Id}", LogType.Debug);
        return normal.Code;
    }

    private void DownloadCaptcha(string url)
    {
        _logger.Log("Скачиваем каптчу", LogType.Debug);
        var imageResult = _httpClient.Send(new HttpRequestMessage(HttpMethod.Get, url));
        imageResult.EnsureSuccessStatusCode();
        var image = imageResult.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult();

        ClearPath();

        var file = File.Create("temp/captcha.jpg");
        file.Write(image);
        _logger.Log("Каптча перезаписана в temp/captcha.jpg", LogType.Debug);
        file.Close();
    }

    private void ClearPath()
    {
        if (!Directory.Exists("temp")) Directory.CreateDirectory("temp");

        if (File.Exists("temp/captcha.jpg")) File.Delete("temp/captcha.jpg");
    }

    public void CaptchaIsFalse()
    {
        _logger.Log($"Неправильная каптча {_lastCaptchaId}", LogType.Error);
        if (string.IsNullOrEmpty(_lastCaptchaId)) return;

        _logger.Log("Отрицательный репорт с ID отослан", LogType.Debug);
        _twoCaptcha.Report(_lastCaptchaId, false);
        _lastCaptchaReported = true;
    }
}
