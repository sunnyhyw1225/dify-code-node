// Program.cs
// Target: .NET 6+
//
// Usage:
//   1. Set your Dify API key:
//      Windows PowerShell:
//        $env:DIFY_API_KEY="app-xxxx"
//      macOS/Linux:
//        export DIFY_API_KEY="app-xxxx"
//
//   2. Run:
//      dotnet run
//
//   3. Enter path to a .json file when prompted.

using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;

class Program
{
    private static readonly string DifyApiKey = "app-qUEcJ1aEt5Le3sKQabp2F9z7";

    private const string DifyBaseUrl = "https://api.dify.ai/v1";

    static async Task Main()
    {
        Console.WriteLine("Dify JSON Workflow Test");
        Console.WriteLine("-----------------------");

        if (string.IsNullOrWhiteSpace(DifyApiKey))
        {
            Console.WriteLine("Error: DIFY_API_KEY environment variable is not set.");
            return;
        }

        Console.Write("Enter .json file path: ");
        string jsonFilePath = Console.ReadLine() ?? "";

        if (string.IsNullOrWhiteSpace(jsonFilePath))
        {
            Console.WriteLine("Error: No file path provided.");
            return;
        }

        if (!File.Exists(jsonFilePath))
        {
            Console.WriteLine($"Error: File not found: {jsonFilePath}");
            return;
        }

        if (!string.Equals(Path.GetExtension(jsonFilePath), ".json", StringComparison.OrdinalIgnoreCase))
        {
            Console.WriteLine("Error: Only .json files are allowed.");
            return;
        }

        try
        {
            using var httpClient = new HttpClient();

            Console.WriteLine();
            Console.WriteLine($"Uploading JSON file: {jsonFilePath}");

            string uploadedFileId = await UploadJsonFileToDifyAsync(
                httpClient,
                jsonFilePath,
                user: "terminal-user"
            );

            Console.WriteLine($"Uploaded file ID: {uploadedFileId}");

            string result = await RunDifyWorkflowAsync(
                httpClient,
                uploadedFileId,
                user: "terminal-user"
            );

            Console.WriteLine();
            Console.WriteLine("Dify Workflow Output:");
            Console.WriteLine("---------------------");
            Console.WriteLine(result);
        }
        catch (Exception ex)
        {
            Console.WriteLine();
            Console.WriteLine("Error:");
            Console.WriteLine(ex.Message);
        }
    }

    static async Task<string> UploadJsonFileToDifyAsync(
        HttpClient httpClient,
        string filePath,
        string user)
    {
        using var form = new MultipartFormDataContent();

        byte[] fileBytes = await File.ReadAllBytesAsync(filePath);

        var fileContent = new ByteArrayContent(fileBytes);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/json");

        form.Add(fileContent, "file", Path.GetFileName(filePath));
        form.Add(new StringContent(user), "user");

        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            $"{DifyBaseUrl}/files/upload"
        );

        request.Headers.Authorization =
            new AuthenticationHeaderValue("Bearer", DifyApiKey);

        request.Content = form;

        using HttpResponseMessage response = await httpClient.SendAsync(request);
        string responseJson = await response.Content.ReadAsStringAsync();

        if (!response.IsSuccessStatusCode)
        {
            throw new Exception(
                $"Dify file upload failed: {(int)response.StatusCode} {response.ReasonPhrase}\n{responseJson}"
            );
        }

        using JsonDocument doc = JsonDocument.Parse(responseJson);

        if (doc.RootElement.TryGetProperty("id", out JsonElement idElement))
        {
            string? id = idElement.GetString();

            if (!string.IsNullOrWhiteSpace(id))
            {
                return id;
            }
        }

        throw new Exception("Could not find uploaded file ID in Dify response:\n" + responseJson);
    }

    static async Task<string> RunDifyWorkflowAsync(
        HttpClient httpClient,
        string uploadedFileId,
        string user)
    {
        string requestJson = BuildWorkflowRequestJson(uploadedFileId, user);

        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            $"{DifyBaseUrl}/workflows/run"
        );

        request.Headers.Authorization =
            new AuthenticationHeaderValue("Bearer", DifyApiKey);

        request.Content = new StringContent(
            requestJson,
            Encoding.UTF8,
            "application/json"
        );

        using HttpResponseMessage response = await httpClient.SendAsync(request);
        string responseJson = await response.Content.ReadAsStringAsync();

        if (!response.IsSuccessStatusCode)
        {
            throw new Exception(
                $"Dify workflow failed: {(int)response.StatusCode} {response.ReasonPhrase}\n{responseJson}"
            );
        }

        return ExtractWorkflowOutput(responseJson);
    }

    static string BuildWorkflowRequestJson(string uploadedFileId, string user)
    {
        var uploadFilesArray = new JsonArray
        {
            new JsonObject
            {
                ["type"] = "document",
                ["transfer_method"] = "local_file",
                ["upload_file_id"] = uploadedFileId
            }
        };

        var inputs = new JsonObject
        {
            ["upload_files"] = uploadFilesArray
        };

        var requestBody = new JsonObject
        {
            ["inputs"] = inputs,
            ["response_mode"] = "blocking",
            ["user"] = user
        };

        return requestBody.ToJsonString();
    }

    static string ExtractWorkflowOutput(string responseJson)
    {
        using JsonDocument doc = JsonDocument.Parse(responseJson);

        JsonElement root = doc.RootElement;

        if (root.TryGetProperty("data", out JsonElement data))
        {
            if (data.TryGetProperty("status", out JsonElement statusElement))
            {
                string? status = statusElement.GetString();

                if (!string.Equals(status, "succeeded", StringComparison.OrdinalIgnoreCase))
                {
                    string errorMessage = "";

                    if (data.TryGetProperty("error", out JsonElement errorElement))
                    {
                        errorMessage = errorElement.ToString();
                    }

                    if (string.IsNullOrWhiteSpace(errorMessage))
                    {
                        errorMessage = $"Workflow status: {status}";
                    }

                    throw new Exception(errorMessage);
                }
            }

            if (data.TryGetProperty("outputs", out JsonElement outputs))
            {
                if (outputs.TryGetProperty("answer", out JsonElement answer))
                {
                    return answer.ToString();
                }

                if (outputs.TryGetProperty("result", out JsonElement result))
                {
                    return result.ToString();
                }

                if (outputs.TryGetProperty("text", out JsonElement text))
                {
                    return text.ToString();
                }

                if (outputs.TryGetProperty("output", out JsonElement output))
                {
                    return output.ToString();
                }

                return outputs.ToString();
            }
        }

        return responseJson;
    }
}