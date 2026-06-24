// File: Program.cs
// Target: .NET 6+
//
// This program:
// 1. Reads user/form inputs from terminal
// 2. Uploads files to Dify
// 3. Runs a Dify workflow
// 4. Prints the workflow result
//
// Required Dify Workflow Start node variables:
//
// requestor
// department
// email
// student_id
// submitted_to_type
// submitted_to_target
// contact_number
// supervisor_advisor_faculty
// upload_files
//
// Recommended Dify Workflow End node output:
//
// answer

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
    private const string DifyApiKey = "YOUR DIFY API KEY";
    private const string DifyBaseUrl = "https://api.dify.ai/v1";

    static async Task Main()
    {
        Console.WriteLine("Dify Workflow Terminal Test");
        Console.WriteLine("---------------------------");

        Console.Write("Requestor: ");
        string requestor = Console.ReadLine() ?? "";

        Console.Write("Department: ");
        string department = Console.ReadLine() ?? "";

        Console.Write("Email: ");
        string email = Console.ReadLine() ?? "";

        Console.Write("Student ID: ");
        string studentId = Console.ReadLine() ?? "";

        Console.Write("Submitted To Type: ");
        string submittedToType = Console.ReadLine() ?? "";

        Console.Write("Submitted To Target: ");
        string submittedToTarget = Console.ReadLine() ?? "";

        Console.Write("Contact Number: ");
        string contactNumber = Console.ReadLine() ?? "";

        Console.Write("Supervisor / Advisor / Faculty: ");
        string supervisorAdvisorFaculty = Console.ReadLine() ?? "";

        Console.WriteLine();
        Console.WriteLine("Enter file paths separated by comma.");
        Console.WriteLine("Example: C:\\Temp\\a.pdf,C:\\Temp\\b.docx");
        Console.Write("File paths, or leave blank for no files: ");

        string filePathsInput = Console.ReadLine() ?? "";

        try
        {
            using var httpClient = new HttpClient();

            List<string> uploadedFileIds = new List<string>();

            if (!string.IsNullOrWhiteSpace(filePathsInput))
            {
                string[] filePaths = filePathsInput.Split(
                    ',',
                    StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries
                );

                foreach (string filePath in filePaths)
                {
                    if (!File.Exists(filePath))
                    {
                        Console.WriteLine($"Skipping missing file: {filePath}");
                        continue;
                    }

                    Console.WriteLine($"Uploading file: {filePath}");

                    string uploadedFileId = await UploadFileToDifyAsync(
                        httpClient,
                        filePath,
                        user: email
                    );

                    uploadedFileIds.Add(uploadedFileId);

                    Console.WriteLine($"Uploaded file ID: {uploadedFileId}");
                }
            }

            string result = await RunDifyWorkflowAsync(
                httpClient: httpClient,
                requestor: requestor,
                department: department,
                email: email,
                studentId: studentId,
                submittedToType: submittedToType,
                submittedToTarget: submittedToTarget,
                contactNumber: contactNumber,
                supervisorAdvisorFaculty: supervisorAdvisorFaculty,
                uploadedFileIds: uploadedFileIds
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

    static async Task<string> UploadFileToDifyAsync(
        HttpClient httpClient,
        string filePath,
        string user)
    {
        using var form = new MultipartFormDataContent();

        byte[] fileBytes = await File.ReadAllBytesAsync(filePath);

        var fileContent = new ByteArrayContent(fileBytes);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue(
            GetContentType(filePath)
        );

        form.Add(fileContent, "file", Path.GetFileName(filePath));
        form.Add(new StringContent(string.IsNullOrWhiteSpace(user) ? "terminal-user" : user), "user");

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
        string requestor,
        string department,
        string email,
        string studentId,
        string submittedToType,
        string submittedToTarget,
        string contactNumber,
        string supervisorAdvisorFaculty,
        List<string> uploadedFileIds)
    {
        string requestJson = BuildWorkflowRequestJson(
            requestor: requestor,
            department: department,
            email: email,
            studentId: studentId,
            submittedToType: submittedToType,
            submittedToTarget: submittedToTarget,
            contactNumber: contactNumber,
            supervisorAdvisorFaculty: supervisorAdvisorFaculty,
            uploadedFileIds: uploadedFileIds
        );

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

    static string BuildWorkflowRequestJson(
        string requestor,
        string department,
        string email,
        string studentId,
        string submittedToType,
        string submittedToTarget,
        string contactNumber,
        string supervisorAdvisorFaculty,
        List<string> uploadedFileIds)
    {
        var uploadFilesArray = new JsonArray();

        foreach (string uploadedFileId in uploadedFileIds)
        {
            uploadFilesArray.Add(new JsonObject
            {
                ["type"] = "document",
                ["transfer_method"] = "local_file",
                ["upload_file_id"] = uploadedFileId
            });
        }

        var inputs = new JsonObject
        {
            ["requestor"] = requestor,
            ["department"] = department,
            ["email"] = email,
            ["student_id"] = studentId,
            ["submitted_to_type"] = submittedToType,
            ["submitted_to_target"] = submittedToTarget,
            ["contact_number"] = contactNumber,
            ["supervisor_advisor_faculty"] = supervisorAdvisorFaculty,
            ["upload_files"] = uploadFilesArray
        };

        var requestBody = new JsonObject
        {
            ["inputs"] = inputs,
            ["response_mode"] = "blocking",
            ["user"] = string.IsNullOrWhiteSpace(email) ? "terminal-user" : email
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

    static string GetContentType(string filePath)
    {
        string extension = Path.GetExtension(filePath).ToLowerInvariant();

        return extension switch
        {
            ".pdf" => "application/pdf",
            ".txt" => "text/plain",
            ".md" => "text/markdown",
            ".csv" => "text/csv",
            ".json" => "application/json",

            ".doc" => "application/msword",
            ".docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",

            ".xls" => "application/vnd.ms-excel",
            ".xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

            ".ppt" => "application/vnd.ms-powerpoint",
            ".pptx" => "application/vnd.openxmlformats-officedocument.presentationml.presentation",

            ".png" => "image/png",
            ".jpg" => "image/jpeg",
            ".jpeg" => "image/jpeg",
            ".webp" => "image/webp",

            ".mp3" => "audio/mpeg",
            ".wav" => "audio/wav",
            ".m4a" => "audio/mp4",

            ".mp4" => "video/mp4",
            ".mov" => "video/quicktime",

            _ => "application/octet-stream"
        };
    }
}