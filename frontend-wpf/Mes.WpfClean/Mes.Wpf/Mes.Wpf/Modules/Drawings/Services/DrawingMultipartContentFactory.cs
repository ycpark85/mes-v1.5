using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;

namespace Mes.Wpf.Modules.Drawings.Services
{
    internal static class DrawingMultipartContentFactory
    {
        public static string? FindMissingFile(params string?[] filePaths)
        {
            foreach (var filePath in filePaths)
            {
                if (!string.IsNullOrWhiteSpace(filePath) && !File.Exists(filePath))
                {
                    return filePath;
                }
            }

            return null;
        }

        public static MultipartFormDataContent CreateSingleFile(
            string fileKind,
            string filePath,
            bool includeKind)
        {
            var content = new MultipartFormDataContent();

            if (includeKind)
            {
                content.Add(new StringContent(fileKind), "file_kind");
            }

            AddFile(content, "file", filePath);
            return content;
        }

        public static MultipartFormDataContent CreateRevisionBundle(
            string revNo,
            bool setAsCurrent,
            string? drawingFilePath,
            string? originalFilePath,
            string? plateFilePath)
        {
            var content = new MultipartFormDataContent
            {
                { new StringContent(revNo), "rev_no" },
                { new StringContent(setAsCurrent ? "true" : "false"), "set_as_current" }
            };

            AddOptionalFile(content, "drawing_file", drawingFilePath);
            AddOptionalFile(content, "original_file", originalFilePath);
            AddOptionalFile(content, "plate_file", plateFilePath);
            return content;
        }

        private static void AddOptionalFile(
            MultipartFormDataContent content,
            string fieldName,
            string? filePath)
        {
            if (!string.IsNullOrWhiteSpace(filePath))
            {
                AddFile(content, fieldName, filePath);
            }
        }

        private static void AddFile(
            MultipartFormDataContent content,
            string fieldName,
            string filePath)
        {
            var stream = File.OpenRead(filePath);
            var fileContent = new StreamContent(stream);
            fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
            content.Add(fileContent, fieldName, Path.GetFileName(filePath));
        }
    }
}
