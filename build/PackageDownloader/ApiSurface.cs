using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.IO;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text;

namespace PackageDownloader
{
    /// <summary>
    /// A hash of an assembly's public API surface: every visible type and every public or protected
    /// member with its signature, sorted, so two builds that expose the same API hash the same even
    /// though their bytes differ (different changeset, MVID, assembly version).
    ///
    /// The generator uses this to decide whether a Server or ModdingKit copy of an assembly adds
    /// anything over the client copy. Only a copy that differs is fed to DocFX a second time.
    /// </summary>
    internal static class ApiSurface
    {
        public const string FileName = "api-surface.json";

        /// <summary>Path relative to <paramref name="root"/> (forward slashes) -> surface hash, for every managed .dll or .exe under it.</summary>
        public static SortedDictionary<string, string> HashAll(string root)
        {
            var result = new SortedDictionary<string, string>(StringComparer.Ordinal);
            // Managed executables (the launcher, the code generators) are assemblies too.
            foreach (var file in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
            {
                var ext = Path.GetExtension(file);
                if (!ext.Equals(".dll", StringComparison.OrdinalIgnoreCase) && !ext.Equals(".exe", StringComparison.OrdinalIgnoreCase))
                    continue;
                var hash = Hash(file);
                if (hash is not null)
                    result[Path.GetRelativePath(root, file).Replace('\\', '/')] = hash;
            }
            return result;
        }

        public static string? Hash(string path)
        {
            using var stream = File.OpenRead(path);
            using var pe = new PEReader(stream);
            if (!pe.HasMetadata)
                return null;
            var md = pe.GetMetadataReader();
            if (!md.IsAssembly)
                return null;

            var lines = new SortedSet<string>(StringComparer.Ordinal);
            var provider = new SignatureProvider();
            foreach (var handle in md.TypeDefinitions)
            {
                var type = md.GetTypeDefinition(handle);
                if (!IsVisible(md, type))
                    continue;
                var name = FullName(md, type);
                var shape = type.Attributes & (TypeAttributes.ClassSemanticsMask | TypeAttributes.Abstract | TypeAttributes.Sealed);
                lines.Add($"T {name} {shape}");

                foreach (var h in type.GetMethods())
                {
                    var m = md.GetMethodDefinition(h);
                    if (!IsVisible(m.Attributes & MethodAttributes.MemberAccessMask))
                        continue;
                    var sig = m.DecodeSignature(provider, null);
                    var isStatic = (m.Attributes & MethodAttributes.Static) != 0 ? " static" : "";
                    lines.Add($"M {name}::{md.GetString(m.Name)}({string.Join(",", sig.ParameterTypes)}):{sig.ReturnType}{isStatic}");
                }
                foreach (var h in type.GetFields())
                {
                    var f = md.GetFieldDefinition(h);
                    if (!IsVisible(f.Attributes & FieldAttributes.FieldAccessMask))
                        continue;
                    lines.Add($"F {name}::{md.GetString(f.Name)}:{f.DecodeSignature(provider, null)}");
                }
                foreach (var h in type.GetProperties())
                {
                    var p = md.GetPropertyDefinition(h);
                    lines.Add($"P {name}::{md.GetString(p.Name)}:{p.DecodeSignature(provider, null).ReturnType}");
                }
                foreach (var h in type.GetEvents())
                    lines.Add($"E {name}::{md.GetString(md.GetEventDefinition(h).Name)}");
            }

            var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("\n", lines)));
            return Convert.ToHexString(bytes).ToLowerInvariant();
        }

        // Public and protected members are what the reference documentation shows.
        private static bool IsVisible(MethodAttributes access) =>
            access is MethodAttributes.Public or MethodAttributes.Family or MethodAttributes.FamORAssem;

        private static bool IsVisible(FieldAttributes access) =>
            access is FieldAttributes.Public or FieldAttributes.Family or FieldAttributes.FamORAssem;

        private static bool IsVisible(MetadataReader md, TypeDefinition type)
        {
            switch (type.Attributes & TypeAttributes.VisibilityMask)
            {
                case TypeAttributes.Public:
                    return true;
                case TypeAttributes.NestedPublic:
                case TypeAttributes.NestedFamily:
                case TypeAttributes.NestedFamORAssem:
                    return IsVisible(md, md.GetTypeDefinition(type.GetDeclaringType()));
                default:
                    return false;
            }
        }

        private static string FullName(MetadataReader md, TypeDefinition type)
        {
            var name = md.GetString(type.Name);
            if (!type.GetDeclaringType().IsNil)
                return FullName(md, md.GetTypeDefinition(type.GetDeclaringType())) + "+" + name;
            var ns = md.GetString(type.Namespace);
            return ns.Length == 0 ? name : ns + "." + name;
        }

        /// <summary>Renders signature types as stable strings; only equality matters, not readability.</summary>
        private sealed class SignatureProvider : ISignatureTypeProvider<string, object?>
        {
            public string GetArrayType(string elementType, ArrayShape shape) => elementType + "[" + new string(',', shape.Rank - 1) + "]";
            public string GetByReferenceType(string elementType) => elementType + "&";
            public string GetFunctionPointerType(MethodSignature<string> signature) => "fnptr(" + string.Join(",", signature.ParameterTypes) + "):" + signature.ReturnType;
            public string GetGenericInstantiation(string genericType, ImmutableArray<string> typeArguments) => genericType + "<" + string.Join(",", typeArguments) + ">";
            public string GetGenericMethodParameter(object? context, int index) => "!!" + index;
            public string GetGenericTypeParameter(object? context, int index) => "!" + index;
            public string GetModifiedType(string modifier, string unmodifiedType, bool isRequired) => unmodifiedType;
            public string GetPinnedType(string elementType) => elementType;
            public string GetPointerType(string elementType) => elementType + "*";
            public string GetPrimitiveType(PrimitiveTypeCode typeCode) => typeCode.ToString();
            public string GetSZArrayType(string elementType) => elementType + "[]";
            public string GetTypeFromDefinition(MetadataReader reader, TypeDefinitionHandle handle, byte rawTypeKind) => FullName(reader, reader.GetTypeDefinition(handle));
            public string GetTypeFromReference(MetadataReader reader, TypeReferenceHandle handle, byte rawTypeKind)
            {
                var t = reader.GetTypeReference(handle);
                var ns = reader.GetString(t.Namespace);
                var name = reader.GetString(t.Name);
                return ns.Length == 0 ? name : ns + "." + name;
            }
            public string GetTypeFromSpecification(MetadataReader reader, object? context, TypeSpecificationHandle handle, byte rawTypeKind) =>
                reader.GetTypeSpecification(handle).DecodeSignature(this, context);
        }
    }
}
