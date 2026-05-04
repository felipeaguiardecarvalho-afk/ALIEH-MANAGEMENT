"use client";

import * as React from "react";
import {
  ColumnDef,
  SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import Link from "next/link";
import { ArrowUpDown, MoreHorizontal, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { formatCurrency, formatDate, formatNumber } from "@/lib/format";
import type { Product } from "@/lib/types";

const columns: ColumnDef<Product>[] = [
  {
    accessorKey: "name",
    header: ({ column }) => (
      <button className="flex items-center gap-2" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}>
        Produto <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => (
      <div>
        <div className="font-medium text-foreground">{row.original.name}</div>
        <div className="text-xs text-muted-foreground">{row.original.productEnterCode || "Sem código de entrada"}</div>
      </div>
    ),
  },
  {
    accessorKey: "sku",
    header: "SKU",
    cell: ({ row }) => <Badge variant="gold">{row.original.sku || "SEM-SKU"}</Badge>,
  },
  {
    accessorKey: "stock",
    header: ({ column }) => (
      <button className="flex items-center gap-2" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}>
        Estoque <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => formatNumber(row.original.stock),
  },
  {
    accessorKey: "price",
    header: ({ column }) => (
      <button className="flex items-center gap-2" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}>
        Preço <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => formatCurrency(row.original.price),
  },
  {
    accessorKey: "style",
    header: "Estilo",
    cell: ({ row }) => row.original.style || "Nao informado",
  },
  {
    accessorKey: "registeredDate",
    header: "Entrada",
    cell: ({ row }) => formatDate(row.original.registeredDate),
  },
  {
    id: "actions",
    cell: ({ row }) => (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={`Ações para ${row.original.name}`}>
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => navigator.clipboard.writeText(row.original.sku || "")}>
            Copiar SKU
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href={`/products/${row.original.id}`}>Ver detalhes</Link>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    ),
  },
];

export function DataTable({ data }: { data: Product[] }) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [search, setSearch] = React.useState("");
  const debouncedSearch = useDebouncedValue(search, 200);

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      globalFilter: debouncedSearch,
    },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: {
      pagination: {
        pageSize: 8,
      },
    },
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-md flex-1">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Buscar por nome, SKU, cor ou estilo..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="pl-10"
          />
        </div>
        <p className="text-sm text-muted-foreground">
          {table.getFilteredRowModel().rows.length} produtos
        </p>
      </div>

      <div className="hidden overflow-hidden rounded-2xl border border-border md:block">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                  Nenhum produto encontrado.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="grid gap-3 md:hidden">
        {table.getRowModel().rows.map((row) => (
          <article key={row.id} className="rounded-2xl border border-border bg-card p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <Badge variant="gold">{row.original.sku || "SEM-SKU"}</Badge>
                <h3 className="mt-3 font-serif text-xl">
                  <Link href={`/products/${row.original.id}`} className="hover:underline">
                    {row.original.name}
                  </Link>
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {row.original.frameColor || "Armação"} / {row.original.lensColor || "Lente"}
                </p>
              </div>
              <p className="text-right font-medium">{formatCurrency(row.original.price)}</p>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
              <span className="rounded-xl bg-white/5 p-2">Estoque {formatNumber(row.original.stock)}</span>
              <span className="rounded-xl bg-white/5 p-2">{row.original.style || "Estilo"}</span>
              <span className="rounded-xl bg-white/5 p-2">{formatDate(row.original.registeredDate)}</span>
            </div>
          </article>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <Button variant="outline" size="sm" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
          Anterior
        </Button>
        <span className="text-sm text-muted-foreground">
          Página {table.getState().pagination.pageIndex + 1} de {table.getPageCount() || 1}
        </span>
        <Button variant="outline" size="sm" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
          Próxima
        </Button>
      </div>
    </div>
  );
}
