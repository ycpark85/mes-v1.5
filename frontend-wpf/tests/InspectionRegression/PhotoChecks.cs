using System.IO;
using System.Reflection;
using Mes.Wpf.Core.Interfaces;
using Mes.Wpf.Core.Models;
using Mes.Wpf.Modules.InspectionSchedules.Dtos;
using Mes.Wpf.Modules.InspectionSchedules.Services;

internal static class PhotoChecks
{
    public static async Task Run(Action<bool, string> check)
    {
        var tempRoot = Path.GetFullPath(Path.GetTempPath());
        var directory = Path.GetFullPath(Path.Combine(tempRoot, "mes-photo-regression-" + Guid.NewGuid().ToString("N")));
        Directory.CreateDirectory(directory);
        try
        {
            var file = Path.Combine(directory, "test.png");
            await File.WriteAllBytesAsync(file, new byte[] { 1, 2, 3 });
            var api = DispatchProxy.Create<IApiClient, RegressionApi>();
            var handler = (RegressionApi)(object)api;
            var messages = new RegressionMessages();
            var opened = new List<string>();
            var photos = new InspectionPhotoService(api, messages, opened.Add, Path.Combine(directory, "cache"));
            var uploaded = false;
            handler.Upload = async content =>
            {
                var part = content.Single();
                uploaded = part.Headers.ContentType?.MediaType == "image/png" && (await part.ReadAsByteArrayAsync()).SequenceEqual(new byte[] { 1, 2, 3 });
                return new ApiResult<DefectAttachmentUploadResponse> { Success = true, Data = new() { FileUri = "fixture", FileName = "test.png", MimeType = "image/png" } };
            };
            var attachment = await photos.UploadAsync(1, file);
            using (File.Open(file, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
                check(uploaded && attachment?.LocalFilePath == file, "photo upload preserves MIME/data and releases the file handle");
            await photos.OpenAsync(attachment);
            check(opened.SequenceEqual(new[] { file }), "newly uploaded local photo opens without downloading");
            await photos.OpenAsync(new());
            check(messages.Warnings.Count == 1 && opened.Count == 1, "unsaved photo without a local file is explained");
            string? downloadPath = null;
            handler.Download = (route, path) =>
            {
                downloadPath = path;
                return Task.FromResult(new ApiResult<bool> { Success = false, Message = "fixture download failed" });
            };
            var stored = new DefectAttachmentEditModel { InspectionDefectAttachmentId = 17, FileName = "../stored.png", MimeType = "image/png" };
            await photos.OpenAsync(stored);
            check(messages.Errors.Count == 1 && opened.Count == 1 && Path.GetDirectoryName(downloadPath) == Path.Combine(directory, "cache"),
                "failed download never opens a file and its cache path stays within the cache directory");
            handler.Download = async (route, path) =>
            {
                await File.WriteAllBytesAsync(path, new byte[] { 4 });
                return new ApiResult<bool> { Success = true, Data = true };
            };
            await photos.OpenAsync(stored);
            check(opened.Last() == downloadPath, "stored photo opens only after successful download");
            handler.Upload = _ => Task.FromResult(new ApiResult<DefectAttachmentUploadResponse> { Success = false, Message = "upload failed" });
            check(await photos.UploadAsync(1, file) is null && messages.Errors.Count == 2, "failed upload creates no attachment");
        }
        finally
        {
            if (!string.Equals(Path.GetDirectoryName(directory)?.TrimEnd(Path.DirectorySeparatorChar), tempRoot.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Unexpected test cleanup path");
            Directory.Delete(directory, recursive: true);
        }
    }
}
