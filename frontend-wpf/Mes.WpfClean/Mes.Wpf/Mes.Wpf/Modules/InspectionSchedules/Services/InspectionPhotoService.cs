using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using Mes.Wpf.Core.Constants;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Modules.InspectionSchedules.Dtos;

namespace Mes.Wpf.Modules.InspectionSchedules.Services;

public sealed class InspectionPhotoService
{
    private readonly IApiClient _api;
    private readonly IMessageService _messages;
    private readonly Action<string> _openFile;
    private readonly string _cacheDirectory;

    public InspectionPhotoService(IApiClient api, IMessageService messages)
        : this(api, messages, path => Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true }),
            Path.Combine(Path.GetTempPath(), "MesWpf", "DefectImages")) { }

    internal InspectionPhotoService(IApiClient api, IMessageService messages, Action<string> openFile, string cacheDirectory)
    {
        _api = api;
        _messages = messages;
        _openFile = openFile;
        _cacheDirectory = cacheDirectory;
    }

    public async Task<DefectAttachmentEditModel?> UploadAsync(long inspectionScheduleId, string filePath)
    {
        using var content = new MultipartFormDataContent();
        using var fileStream = File.OpenRead(filePath);
        using var streamContent = new StreamContent(fileStream);
        streamContent.Headers.ContentType = new MediaTypeHeaderValue(Path.GetExtension(filePath).ToLowerInvariant() switch
        {
            ".jpg" or ".jpeg" => "image/jpeg", ".png" => "image/png", ".bmp" => "image/bmp",
            ".webp" => "image/webp", _ => "application/octet-stream"
        });
        content.Add(streamContent, "file", Path.GetFileName(filePath));
        var result = await _api.PostMultipartAsync<DefectAttachmentUploadResponse>(
            $"{ApiRoutes.InspectionSchedules}/{inspectionScheduleId}/result/photos", content);
        if (!result.Success || result.Data is null)
        {
            _messages.ShowError(result.Message ?? "불량사진 업로드에 실패했습니다.");
            return null;
        }
        return new DefectAttachmentEditModel
        {
            FileUri = result.Data.FileUri, FileName = result.Data.FileName,
            MimeType = result.Data.MimeType ?? "", Memo = "", LocalFilePath = filePath
        };
    }

    public async Task OpenAsync(DefectAttachmentEditModel? attachment)
    {
        if (attachment is null) return;
        if (!string.IsNullOrWhiteSpace(attachment.LocalFilePath) && File.Exists(attachment.LocalFilePath))
        {
            _openFile(attachment.LocalFilePath);
            return;
        }
        if (!attachment.InspectionDefectAttachmentId.HasValue)
        {
            _messages.ShowWarning("저장된 이미지 정보가 없습니다.");
            return;
        }
        var extension = Path.GetExtension(attachment.FileName);
        if (string.IsNullOrWhiteSpace(extension))
            extension = attachment.MimeType?.ToLowerInvariant() switch
            {
                "image/png" => ".png", "image/bmp" => ".bmp", "image/webp" => ".webp", _ => ".jpg"
            };
        Directory.CreateDirectory(_cacheDirectory);
        var safeFileName = Path.GetFileName(attachment.FileName);
        if (string.IsNullOrWhiteSpace(safeFileName))
            safeFileName = $"inspection_attachment_{attachment.InspectionDefectAttachmentId}{extension}";
        else if (string.IsNullOrWhiteSpace(Path.GetExtension(safeFileName)))
            safeFileName += extension;
        var path = Path.Combine(_cacheDirectory, safeFileName);
        var result = await _api.DownloadFileAsync(
            $"{ApiRoutes.InspectionSchedules}/result/attachments/{attachment.InspectionDefectAttachmentId}/content", path);
        if (!result.Success)
        {
            _messages.ShowError(result.Message ?? "이미지 다운로드에 실패했습니다.");
            return;
        }
        _openFile(path);
    }
}
